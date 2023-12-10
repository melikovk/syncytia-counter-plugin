import os.path
import json

from java.lang import Runnable, Thread
from javax.swing import (JPanel, JFrame, JButton, JTextField, JCheckBox,
                         JLabel, JScrollPane, BorderFactory, ButtonGroup,
                         JComboBox, JRadioButton, JSeparator, WindowConstants,
                         SwingUtilities)
from java.awt import GridBagLayout, GridBagConstraints, GridLayout, Insets
from java.awt.event import MouseAdapter

from ij import WindowManager, IJ, ImageListener, ImagePlus
from ij.gui import Toolbar, ImageCanvas, PointRoi, Overlay
from ij.measure import ResultsTable
from ij.io import SaveDialog, OpenDialog

#
# Define Global Constants
#

MARKER_SIZES = ["Tiny", "Small", "Medium", "Large", "XL", "XXL", "XXXL"]
MARKER_SHAPES = ["Hybrid", "Cross", "Dot", "Circle"]
DEFAULT_SHOW_NUMBERS = True
DEFAULT_SIZE = 2
DEFAULT_SHAPE = PointRoi.DOT
ROI_LIMIT = 100


class SyncytiaRoi:
    """ Wrap PointRoi with additional methods

    Each syncytia is associated with separate counter in PontRoi.
    Number of different counters in PointRoi is limited to 100, therefore we
    need to add additional PointRoi's if we have more than 100 syncytia.
    We use separate PointRoi for single cells.
    Because PointRoi incorrectly reports point count for the counter with the
    index=0 in multi-point mode we have to correct the output (subtruct 1 if the
    count is larger than 0).
    Because PointRoi automatically reverts from multi-point mode to simple mode 
    when the only points that are left have counter index=0 we add dummy point
    with maximal counter index (99 or ROI_LIMIT-1) and correct for this point 
    for this counter index
    """

    def __init__(
        self,
        markers=None,
        marker_size=DEFAULT_SIZE,
        marker_type=DEFAULT_SHAPE,
        show_labels=DEFAULT_SHOW_NUMBERS,
    ):
        self.single_cells = PointRoi()
        self.single_cells.setCounter(ROI_LIMIT - 1)
        self.single_cells.addPoint(-10, -10)
        self.roi = []
        self.saved = [self.single_cells]
        self.active_roi = self.single_cells
        self.syncytia_count = 1
        self.overlay = Overlay(self.active_roi)
        self.set_markers(marker_size, marker_type, show_labels)
        if markers is not None:
            self.add_markers(markers)

    def set_syncytium(self, idx):
        if idx == 0:
            self.active_roi = self.single_cells
            self.active_roi.setCounter(0)
        else:
            q, r = divmod(idx - 1, ROI_LIMIT)
            while q + 1 > len(self.roi):
                self.append_roi()
            self.active_roi = self.roi[q]
            self.active_roi.setCounter(r)
            if idx >= self.syncytia_count:
                self.syncytia_count = idx + 1

    def clear_syncytium(self, idx):
        if self.nuclei_count(idx) == 0:
            return
        self.overlay.remove(self.active_roi)
        if idx == 0:
            self.single_cells = PointRoi()
            self.active_roi = self.single_cells
        else:
            q, r = divmod(idx - 1, ROI_LIMIT)
            roi = PointRoi()
            for idx, p in enumerate(self.active_roi.getContainedPoints()):
                counter = self.active_roi.getCounter(idx)
                if counter != r:
                    roi.setCounter(counter)
                    roi.addPoint(p.x, p.y)
            self.roi[q] = roi
            self.active_roi = roi
        self.overlay.add(self.active_roi)
        self.update_markers()

    def nuclei_count(self, idx):
        """
        Because PointRoi incorrectly reports point count for the counter with 
        the index=0 in multi-point mode we have to correct the output 
        (subtruct 1 if the count is larger than 0).
        Similarly we correct for the index=ROI_LIMIT to correct for the dummy 
        initial point

        """
        if idx == 0:
            n = self.single_cells.getCount(0)
        else:
            q, r = divmod(idx - 1, ROI_LIMIT)
            if q + 1 > len(self.roi):
                return 0
            if (r == ROI_LIMIT - 1):
                n = self.roi[q].getCount(r) - 1
            else:
                n = self.roi[q].getCount(r)
        return n

    def is_saved(self):
        if len(self.roi) + 1 != len(self.saved):
            return False
        for roi, saved in zip(self.roi + [self.single_cells], self.saved):
            if roi.getNCoordinates() != saved.getNCoordinates():
                return False
            points = roi.getContainedPoints()
            other_points = saved.getContainedPoints()
            for i in range(roi.getNCoordinates()):
                if (points[i] != other_points[i]
                        or roi.getCounter(i) != saved.getCounter(i)):
                    return False
        return True

    def append_roi(self):
        roi = PointRoi()
        roi.setCounter(ROI_LIMIT - 1)
        roi.addPoint(-10, -10)
        self.roi.append(roi)
        self.overlay.add(roi)
        self.set_markers(
            self.marker_size,
            self.marker_type,
            self.show_labels,
            -1,
        )

    def set_roi_markers(self, roi):
        roi.setSize(self.marker_size)
        roi.setPointType(self.marker_type)
        roi.setShowLabels(self.show_labels)

    def set_markers(
        self,
        marker_size,
        marker_type,
        show_labels,
        roi_idx=None,
    ):
        self.marker_size = marker_size
        self.marker_type = marker_type
        self.show_labels = show_labels
        if roi_idx is None:
            for roi in self.roi:
                self.set_roi_markers(roi)
            self.set_roi_markers(self.single_cells)
            self.single_cells.setShowLabels(False)
        else:
            self.set_roi_markers(self.roi[roi_idx])

    def is_empty(self):
        result = (all([roi.getNCoordinates() == 0 for roi in self.roi])
                  and self.single_cells.getNCoordinates() == 0)
        return result

    def add_markers(self, markers):
        """Load markers from json file. Return None if file format is not 
        correct.
        """
        syncytia_count = 1
        for marker in markers:
            if marker['idx'] == 0:
                self.single_cells.setCounter(0)
                self.single_cells.addPoint(*marker['position'])
            else:
                q, r = divmod(marker['idx'] - 1, ROI_LIMIT)
                while q + 1 > len(self.roi):
                    self.append_roi()
                self.roi[q].setCounter(r)
                self.roi[q].addPoint(*marker['position'])
                if marker['idx'] >= syncytia_count:
                    syncytia_count = marker['idx'] + 1
        self.syncytia_count = syncytia_count

    def update_saved(self):
        self.saved = [roi.clone() for roi in self.roi]
        self.saved.append(self.single_cells.clone())

    def to_json(self):
        """ Save markers to json file
        Ignore first dummy point in each of the PointRoi
        """
        # Save single cells
        markers = [{
            'idx': 0,
            'position': (p.x, p.y)
        } for p in self.single_cells.getContainedPoints()][1:]
        # Save syncytia
        for roi_idx, roi in enumerate(self.roi):
            markers += [{
                'idx': ROI_LIMIT * roi_idx + roi.getCounter(idx) + 1,
                'position': (p.x, p.y)
            } for idx, p in enumerate(roi.getContainedPoints())][1:]
        return markers

    def get_table(self):
        table = ResultsTable()
        max_idx = self.syncytia_count
        count = self.nuclei_count(0)
        table.addValue("Count", count)
        table.addLabel("Single cells")
        table.incrementCounter()
        for idx in range(1, max_idx + 1):
            count = self.nuclei_count(idx)
            if count > 0:
                table.addValue("Count", count)
                table.addLabel("Syncytium {}".format(table.getCounter() - 1))
                table.incrementCounter()
        table.deleteRow(table.getCounter() - 1)
        return table


class FusionClickListener(MouseAdapter):

    def __init__(self, ic):
        super(FusionClickListener, self).__init__()
        self.ic = ic

    def mouseClicked(self, event):
        pass

    def mouseEntered(self, event):
        if (not IJ.spaceBarDown()
                and not Toolbar.getToolId() == Toolbar.MAGNIFIER
                and not Toolbar.getToolId() == Toolbar.HAND):
            Toolbar.getInstance().setTool("multipoint")

    def mouseExited(self, event):
        pass

    def mousePressed(self, event):
        pass

    def mouseReleased(self, event):
        pass


class SyncytiaCounter(JFrame, Runnable, ImageListener):

    def __init__(self):
        super(JFrame, self).__init__(
            "Syncytia Counter",
            windowClosing=self.close,
            defaultCloseOperation=WindowConstants.DO_NOTHING_ON_CLOSE)
        self.syncytia = SyncytiaRoi()
        self.imp = None
        self.next_idx = 0
        self.count_labels = []
        self.radio_buttons = []
        self.output_buttons = []
        self.build_gui()
        ImagePlus.addImageListener(self)
        # Create and start a thread to update GUI
        self.is_alive = True
        self.thread = Thread(self)
        self.thread.start()

    def build_gui(self):
        # Build panel with control buttons
        action_panel = JPanel()
        action_panel.setBorder(BorderFactory.createTitledBorder("Actions"))
        action_panel.setLayout(GridBagLayout())
        constraints = GridBagConstraints()
        constraints.gridwidth = GridBagConstraints.REMAINDER
        constraints.fill = GridBagConstraints.HORIZONTAL
        constraints.insets = Insets(2, 2, 2, 2)
        self.action_panel = action_panel
        # Add "Link Image" Button
        link_button = JButton("Link Image",
                              enabled=True,
                              actionPerformed=self.link_image)
        action_panel.add(link_button, constraints)
        self.link_button = link_button
        self.output_buttons.append(link_button)
        # Add "Load Markers" button
        load_button = JButton("Load Markers",
                              actionPerformed=self.load_markers)
        action_panel.add(load_button, constraints)
        self.output_buttons.append(load_button)
        # Add separator
        action_panel.add(JSeparator(), constraints)
        # Add "Add Syncytium" Button
        add_button = JButton("Add Syncytium",
                             enabled=False,
                             actionPerformed=self.add_syncytium)
        action_panel.add(add_button, constraints)
        # Add "Clear this syncytium" button
        clearthis_button = JButton("Clear This Syncytium",
                                   enabled=False,
                                   actionPerformed=self.clear_syncytium)
        action_panel.add(clearthis_button, constraints)
        # Add "Clear All" button
        clearall_button = JButton("Clear All",
                                  enabled=False,
                                  actionPerformed=self.clear_all_syncytia)
        action_panel.add(clearall_button, constraints)
        # Add separator
        action_panel.add(JSeparator(), constraints)
        # Add "Show Numbers" checkbox
        show_numbers_box = JCheckBox("Show Numbers",
                                     selected=True,
                                     enabled=False,
                                     actionPerformed=self.update_markers)
        action_panel.add(show_numbers_box, constraints)
        self.show_numbers = show_numbers_box
        # Add "Hide Markers" checkbox
        hide_box = JCheckBox("Hide Markers",
                             selected=False,
                             enabled=False,
                             actionPerformed=self.hide_markers)
        action_panel.add(hide_box, constraints)
        self.hide_box = hide_box
        # Add "Hide Single Cells" checkbox
        hide_single_box = JCheckBox("Hide Single Cells",
                                    selected=False,
                                    enabled=False,
                                    actionPerformed=self.hide_single_cells)
        action_panel.add(hide_single_box, constraints)
        self.hide_single_box = hide_single_box
        # Add "Marker Size"
        marker_size_label = JLabel("Marker Size", JLabel.CENTER, enabled=False)
        marker_size_combo = JComboBox(MARKER_SIZES,
                                      enabled=False,
                                      selectedIndex=DEFAULT_SIZE,
                                      itemStateChanged=self.update_markers)
        action_panel.add(marker_size_label, constraints)
        action_panel.add(marker_size_combo, constraints)
        self.marker_size = marker_size_combo
        # Add "Marker Shape"
        marker_shape_label = JLabel("Marker Shape",
                                    JLabel.CENTER,
                                    enabled=False)
        marker_shape_combo = JComboBox(MARKER_SHAPES,
                                       enabled=False,
                                       selectedIndex=DEFAULT_SHAPE,
                                       itemStateChanged=self.update_markers)
        action_panel.add(marker_shape_label, constraints)
        action_panel.add(marker_shape_combo, constraints)
        self.marker_shape = marker_shape_combo
        # Add separator
        action_panel.add(JSeparator(), constraints)
        # Add "Counts Table" button
        counts_button = JButton("Results", actionPerformed=self.counts_table)
        action_panel.add(counts_button, constraints)
        self.output_buttons.append(counts_button)
        # Add "Save Markers" button
        save_button = JButton("Save Markers",
                              actionPerformed=self.save_markers)
        action_panel.add(save_button, constraints)
        self.output_buttons.append(save_button)
        # Build panel with syncytia counts
        syncytia_panel = JPanel()
        syncytia_panel.setBorder(BorderFactory.createTitledBorder("Syncytia"))
        syncytia_layout = GridLayout(0, 2)
        syncytia_panel.setLayout(syncytia_layout)
        self.syncytia_panel = syncytia_panel
        self.syncytia_group = ButtonGroup()
        scroll_pane = JScrollPane(syncytia_panel, 22, 31)
        self.scroll_pane = scroll_pane
        # Add "Single cell" radiobutton and label
        self.add_counter()
        # Add panels to frame
        constraints = GridBagConstraints()
        self.getContentPane().setLayout(GridBagLayout())
        constraints.anchor = GridBagConstraints.NORTH
        self.getContentPane().add(scroll_pane, constraints)
        self.getContentPane().add(action_panel, constraints)
        # Add status line
        self.status_line = JTextField(enabled=False)
        constraints.gridy = 1
        constraints.gridwidth = GridBagConstraints.REMAINDER
        constraints.fill = GridBagConstraints.HORIZONTAL
        self.getContentPane().add(self.status_line, constraints)
        self.pack()
        self.setLocation(1000, 200)
        # Set minimal sizes
        self.setMinimumSize(self.getSize())
        action_panel.setMinimumSize(action_panel.getSize())
        size = scroll_pane.getSize()
        size.height = action_panel.getSize().height
        scroll_pane.setMinimumSize(size)
        self.setVisible(True)

    def link_image(self, event=None):
        imp = WindowManager.getCurrentImage()
        if imp is None:
            IJ.noImage()
        else:
            if self.imp is not None:
                self.unlink_image()
            ic = imp.getCanvas()
            ic.addMouseListener(FusionClickListener(ic))
            imp.setRoi(self.syncytia.active_roi)
            imp.setOverlay(self.syncytia.overlay)
            self.imp = imp
            self.status_line.setText(imp.getTitle())
            self.update_button_states()
            self.update_syncytia_panel()
            self.update_markers()
            self.update_markers_view()

    def update_button_states(self):
        if self.imp is not None:
            for component in self.action_panel.getComponents():
                component.setEnabled(True)
            for rb in self.syncytia_group.getElements():
                rb.setEnabled(True)
        else:
            for component in self.action_panel.getComponents():
                component.setEnabled(False)
            for rb in self.syncytia_group.getElements():
                rb.setEnabled(False)
            for component in self.output_buttons:
                component.setEnabled(True)

    def hide_markers(self, event=None):
        if self.hide_box.isSelected():
            self.imp.deleteRoi()
            self.imp.setHideOverlay(True)
        else:
            self.imp.setRoi(self.syncytia.active_roi)
            self.imp.setHideOverlay(False)

    def hide_single_cells(self, event=None):
        if self.hide_single_box.isSelected():
            self.syncytia.overlay.remove(self.syncytia.single_cells)
        elif not self.syncytia.overlay.contains(self.syncytia.single_cells):
            self.syncytia.overlay.add(self.syncytia.single_cells)
        self.imp.getCanvas().repaintOverlay()

    def add_syncytium(self, event=None):
        self.add_counter()
        self.radio_buttons[-1].setSelected(True)
        self.update_syncytia_panel()

    def add_counter(self):
        if self.next_idx == 0:
            name = "Single Cells       "
        else:
            name = "Syncytium {}".format(self.next_idx - 1)
        rb = JRadioButton(name,
                          enabled=(self.imp is not None),
                          selected=(self.imp is not None),
                          actionCommand=str(self.next_idx),
                          itemStateChanged=self.select_syncytium)
        label = JTextField("{}".format(0), enabled=False, editable=False)
        label.setHorizontalAlignment(JTextField.CENTER)
        self.syncytia_group.add(rb)
        self.syncytia_panel.add(rb)
        self.syncytia_panel.add(label)
        self.radio_buttons.append(rb)
        self.count_labels.append(label)
        self.next_idx += 1

    def remove_counter(self):
        rb = self.radio_buttons.pop()
        label = self.count_labels.pop()
        self.syncytia_group.remove(rb)
        self.syncytia_panel.remove(rb)
        self.syncytia_panel.remove(label)
        self.next_idx -= 1

    def update_syncytia_panel(self):
        while self.next_idx < self.syncytia.syncytia_count:
            self.add_counter()
        while self.next_idx > self.syncytia.syncytia_count:
            self.remove_counter()
        self.radio_buttons[-1].setSelected(self.imp is not None)
        size = self.scroll_pane.getPreferredSize()
        max_height = self.action_panel.getMinimumSize().height
        if size.height > max_height:
            size.height = max_height
            self.scroll_pane.setPreferredSize(size)
        else:
            self.scroll_pane.setPreferredSize(None)
        self.revalidate()
        new_height = self.scroll_pane.getVerticalScrollBar().getMaximum()
        self.scroll_pane.getVerticalScrollBar().setValue(new_height)

    def select_syncytium(self, event=None):
        counter_idx = int(
            self.syncytia_group.getSelection().getActionCommand())
        self.syncytia.set_syncytium(counter_idx)
        self.imp.setRoi(self.syncytia.active_roi)

    def clear_syncytium(self, event=None):
        counter_idx = int(
            self.syncytia_group.getSelection().getActionCommand())
        self.syncytia.clear_syncytium(counter_idx)
        self.imp.setRoi(self.syncytia.active_roi)

    def clear_all_syncytia(self, event=None):
        if IJ.showMessageWithCancel("WARNING", "CLEAR ALL SYNCYTIA?"):
            self.syncytia = SyncytiaRoi(
                marker_size=self.marker_size.getSelectedIndex(),
                marker_type=self.marker_shape.getSelectedIndex(),
                show_labels=self.show_numbers.isSelected())
            self.update_syncytia_panel()
            self.update_markers()
            self.update_markers_view()

    def update_markers(self, event=None):
        size = self.marker_size.getSelectedIndex()
        shape = self.marker_shape.getSelectedIndex()
        show_numbers = self.show_numbers.isSelected()
        self.syncytia.set_markers(size, shape, show_numbers)
        self.imp.getCanvas().repaintOverlay()

    def update_markers_view(self):
        self.imp.setRoi(self.syncytia.active_roi)
        self.imp.setOverlay(self.syncytia.overlay)
        self.hide_markers()
        self.hide_single_cells()

    def load_markers(self, event=None):
        if (not self.syncytia.is_saved() and not IJ.showMessageWithCancel(
                "WARNING", "THIS WILL CLEAR EXISTING MARKERS")):
            return
        filedialog = OpenDialog('Load Markers from json File', "")
        if filedialog.getPath():
            fname, fdir = filedialog.getFileName(), filedialog.getDirectory()
            fpath = os.path.join(fdir, fname)
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                if data.get("format") != "markers":
                    IJ.showMessage(
                        "Wrong format of the file {}!".format(fname))
                    return
                else:
                    self.syncytia = SyncytiaRoi(
                        markers=data['data'],
                        marker_size=self.marker_size.getSelectedIndex(),
                        marker_type=self.marker_shape.getSelectedIndex(),
                        show_labels=self.show_numbers.isSelected())
                    self.syncytia.update_saved()
            except IOError:
                IJ.showMessage("Could not open a file: " + fname)
            except ValueError:
                IJ.showMessage("File {} is not in json format.".format(fname))
            self.update_syncytia_panel()
            if self.imp is not None:
                self.select_syncytium()
                self.update_markers()
                self.update_markers_view()

    def counts_table(self, event=None):
        table = self.syncytia.get_table()
        table.show("SyncytiaCount")

    def save_markers(self, event=None):
        if self.syncytia.is_empty():
            IJ.showMessage("There are no markers, Nothing to save")
            return
        fname = os.path.splitext(self.status_line.getText())[0] + '_markers'
        filedialog = SaveDialog('Select filename to save', fname, ".json")
        if filedialog.getFileName():
            fpath = filedialog.getDirectory() + filedialog.getFileName()
            markers = self.syncytia.to_json()
            try:
                with open(fpath, 'w') as f:
                    json.dump({"format": "markers", "data": markers}, f)
                self.syncytia.update_saved()
            except IOError:
                IJ.showMessage(
                    "Could not save the file. Markers are not saved")

    def update_counts(self):
        self.count_labels[0].setText("{}".format(
            self.syncytia.nuclei_count(0)))
        for idx in range(1, self.next_idx):
            self.count_labels[idx].setText("{}".format(
                self.syncytia.nuclei_count(idx)))

    def run(self):
        while self.is_alive:
            self.update_counts()
            self.thread.sleep(100)

    def close(self, event=None):
        if (self.syncytia.is_saved() or IJ.showMessageWithCancel(
                "WARNING", "MARKERS ARE NOT SAVED! EXIT WITHOUT SAVING?")):
            ImagePlus.removeImageListener(self)
            self.unlink_image()
            self.is_alive = False
            self.thread.join()
            self.dispose()

    def unlink_image(self):
        if self.imp is not None and self.imp.isVisible():
            ic = self.imp.getCanvas()
            for ml in ic.getMouseListeners():
                if isinstance(ml, FusionClickListener):
                    ic.removeMouseListener(ml)
            self.imp.setOverlay(None)
            self.imp.setRoi(None)
        self.imp = None
        self.update_button_states()

    def imageClosed(self, imp):
        if imp == self.imp:
            self.unlink_image()

    def imageOpened(self, imp):
        pass

    def imageUpdated(self, imp):
        pass


if __name__ in ['__main__', '__builtin__']:
    SyncytiaCounter()
