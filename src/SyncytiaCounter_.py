import os.path
import json

from java.lang import Runnable
from java.util.concurrent import Executors, TimeUnit
from javax.swing import (JPanel, JFrame, JButton, JTextField, JCheckBox, JLabel,
    JScrollPane, BorderFactory, ButtonGroup, JComboBox, JRadioButton, 
    JSeparator, WindowConstants)
from java.awt import GridBagLayout, GridBagConstraints, GridLayout, Insets
from java.awt.event import MouseAdapter, WindowAdapter

from ij import WindowManager, IJ
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

class SyncytiaRoi:
    """ Wrap PointRoi with additional methods
    """

    def __init__(self, 
                 marker_size=DEFAULT_SIZE,
                 marker_type=DEFAULT_SHAPE,
                 show_labels=DEFAULT_SHOW_NUMBERS):
        self._single_cells = PointRoi(-10,-10)
        self._roi = []
        self._saved = [self._single_cells]
        self.active_roi = self._single_cells
        self._roi_limit = 10
        self.syncytia_count = 1
        self.overlay = Overlay(self.active_roi)
        self.marker_size = marker_size
        self.marker_type = marker_type
        self.show_labels = show_labels
        self.update_markers

    def set_syncytium(self, idx):
        if idx == 0:
            self.active_roi = self._single_cells
            self.active_roi.setCounter(0)
        else:
            q, r = divmod(idx - 1, self._roi_limit)
            while q + 1 > len(self._roi):
                self.append_roi()
            self.active_roi = self._roi[q]
            self.active_roi.setCounter(r)
            if idx >= self.syncytia_count:
                self.syncytia_count = idx + 1

    def get_nuclei_count(self, idx):
        if idx == 0:
            n = self._single_cells.getCount(0) - 1
        else:
            q, r = divmod(idx - 1, self._roi_limit)
            if q + 1 > len(self._roi):
                return 0
            if r > 0:
                n = self._roi[q].getCount(r)
            else:
                n = self._roi[q].getCount(r) - 1
        return n

    def is_saved(self):
        if len(self._roi) + 1 != len(self._saved):
            return False
        for roi, saved in zip(self._roi + [self._single_cells], self._saved):
            if roi.getNCoordinates() != saved.getNCoordinates():
                return False
            points = roi.getContainedPoints()
            other_points = saved.getContainedPoints()
            for i in range(roi.getNCoordinates()):
                if (points[i] != other_points[i] or
                    roi.getCounter(i) != saved.getCounter(i)):
                    return False
        return True

    def append_roi(self):
        roi = PointRoi(-10,-10)
        roi.setSize(self.marker_size)
        roi.setPointType(self.marker_type)
        roi.setShowLabels(self.show_labels)
        roi.setCounter(99)
        self._roi.append(roi)
        self.overlay.add(roi)

    def set_markers(self, marker_size, marker_type, show_labels):
        self.marker_size = marker_size
        self.marker_type = marker_type
        self.show_labels = show_labels
        self.update_markers()
        
    def update_markers(self):
        for roi in self._roi:
            roi.setSize(self.marker_size)
            roi.setPointType(self.marker_type)
            roi.setShowLabels(self.show_labels)
        self._single_cells.setSize(self.marker_size)
        self._single_cells.setPointType(self.marker_type)
        self._single_cells.setShowLabels(False)

    def is_empty(self):
        result = (all([roi.getNCoordinates() == 1 for roi in self._roi])
            and self._single_cells.getNCoordinates() == 1)
        return result 

    def from_json(self, fpath):
        """Load markers from json file. Return None if file format is not 
        correct.
        """
        with open(fpath, 'r') as f:
            data = json.load(f)
        if data.get("format") != "markers":
            IJ.showDialog("Wrong format of the file!")
            return
        self.reset()
        syncytia_count = 1
        for marker in data['data']:
            if marker['idx'] == 0:
                self._single_cells.addPoint(*marker['position'])
            else:
                q, r = divmod(marker['idx'] - 1, self._roi_limit)
                while q + 1 > len(self._roi):
                    self.append_roi()
                self._roi[q].setCounter(r)
                self._roi[q].addPoint(*marker['position'])
                if marker['idx'] >= syncytia_count:
                    syncytia_count = marker['idx'] + 1
        self.syncytia_count = syncytia_count 
        self._saved = [roi.clone() for roi in self._roi]
        self._saved.append(self._single_cells.clone())
        
    def to_json(self, fpath):
        """ Save markers to json file
        """
        # Save single cells
        syncytia = [{'idx': idx, 'position': (p.x, p.y)} 
            for p in self._single_cells.getContainedPoints()[1:]]
        # Save syncytia
        indexes = []
        points = []
        for idx, roi in enumerate(self._roi):
            indexes += [self._roi_limit * idx + i & 255 + 1 
                for i in roi.getCounters()[1:]]
            points += [(p.x, p.y) for p in roi.getContainedPoints()[1:]]
        syncytia += [{'idx': idx, 'position':p} 
            for idx, p in zip(indexes, points)]
        with open(fpath, 'w') as f:
            json.dump({"format":"markers", "data":syncytia}, f)
        self._saved = [roi.clone() for roi in self._roi]

    def get_table(self):
        table = ResultsTable()
        max_idx = self.syncytia_count
        count = self.get_nuclei_count(0)
        table.addValue("Count", count)
        table.addLabel("Single cells")
        table.incrementCounter()
        for idx in range(1, max_idx + 1):
            count = self.get_nuclei_count(idx)
            if count > 0:
                table.addValue("Count", count)
                table.addLabel("Syncytium {}".format(table.getCounter() - 1))
                table.incrementCounter()
        table.deleteRow(table.getCounter() - 1)
        return table

    def reset(self):
        self._single_cells = PointRoi(-10,-10)
        self._roi = []
        self.syncytia_count = 1
        self._saved = [self._single_cells]
        self.active_roi = self._single_cells
        self.overlay = Overlay()
        self.overlay.add(self.active_roi)

class ImageClosingListener(WindowAdapter):
    def __init__(self, gui):
        self.gui = gui

    def windowClosed(self, event):
        self.gui.unlink_image()

class FusionClickListener(MouseAdapter):
    def __init__(self, ic):
        super(FusionClickListener, self).__init__()
        self.ic = ic

    def mouseClicked(self, event):
        ImageCanvas.mouseClicked(self.ic, event)

    def mouseEntered(self, event):
        if (IJ.spaceBarDown() or
            Toolbar.getToolId() == Toolbar.MAGNIFIER or
            Toolbar.getToolId() == Toolbar.HAND):
            ImageCanvas.mouseEntered(self.ic, event)
        else:
            Toolbar.getInstance().setTool("multipoint")
            ImageCanvas.mouseEntered(self.ic, event)

    def mouseExited(self, event):
        ImageCanvas.mouseExited(self.ic, event)

    def mousePressed(self, event):
        ImageCanvas.mousePressed(self.ic, event)

    def mouseReleased(self, event):
        ImageCanvas.mouseReleased(self.ic, event)

class SyncytiaCounter(JFrame, Runnable):
    def __init__(self):
        super(JFrame, self).__init__("Syncytia Counter",
            windowClosing=self.close,
            defaultCloseOperation=WindowConstants.DO_NOTHING_ON_CLOSE)
        self.syncytia = SyncytiaRoi()
        self.imp = None
        self.next_idx = 0
        self.count_labels = []
        self.radio_buttons = []
        self.action_buttons = []
        self.output_buttons = []
        self.build_gui()
        # Add executor
        self.scheduled_executor = Executors.newSingleThreadScheduledExecutor()
        time_offset_to_start = 1000
        time_between_runs = 100
        self.scheduled_executor.scheduleWithFixedDelay(self,
            time_offset_to_start, time_between_runs, TimeUnit.MILLISECONDS)

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
        link_button = JButton(
            "Link Image",
            enabled=True,
            actionPerformed=self.link_image)
        action_panel.add(link_button, constraints)
        self.link_button = link_button
        # Add separator
        action_panel.add(JSeparator(), constraints)
        # Add "Add Syncytium" Button
        add_button = JButton(
            "Add Syncytium",
            enabled=False,
            actionPerformed=self.add_syncytium)
        action_panel.add(add_button, constraints)
        self.action_buttons.append(add_button)
        # Add "Clear this syncytium" button
        clearthis_button = JButton(
            "Clear This Syncytium",
            enabled=False,
            actionPerformed=self.clear_syncytium)
        action_panel.add(clearthis_button, constraints)
        self.action_buttons.append(clearthis_button)
        # Add "Clear All" button
        clearall_button = JButton(
            "Clear All",
            enabled=False,
            actionPerformed=self.clear_all_syncytia)
        action_panel.add(clearall_button, constraints)
        self.action_buttons.append(clearall_button)
        # Add "Load Markers" button
        load_button = JButton(
            "Load Markers",
            enabled=False,
            actionPerformed=self.load_markers)
        action_panel.add(load_button, constraints)
        self.action_buttons.append(load_button)
        # Add separator
        action_panel.add(JSeparator(), constraints)
        # Add "Show Numbers" checkbox
        show_numbers_box = JCheckBox(
            "Show Numbers",
            selected=True,
            enabled=False,
            actionPerformed=self.update_markers)
        action_panel.add(show_numbers_box, constraints)
        self.show_numbers = show_numbers_box
        # Add "Hide Markers" checkbox
        hide_box = JCheckBox(
            "Hide Markers",
            selected=False,
            enabled=False,
            actionPerformed=self.hide_markers)
        action_panel.add(hide_box, constraints)
        self.hide_box = hide_box
        # Add "Hide Single Cells" checkbox
        hide_single_box = JCheckBox(
            "Hide Single Cells",
            selected=False,
            enabled=False,
            actionPerformed=self.hide_single_cells)
        action_panel.add(hide_single_box, constraints)
        self.hide_single_box = hide_single_box
        # Add "Marker Size"
        marker_size_label = JLabel("Marker Size", JLabel.CENTER, enabled=False)
        marker_size_combo = JComboBox(
            MARKER_SIZES,
            enabled=False,
            selectedIndex=DEFAULT_SIZE,
            itemStateChanged=self.update_markers)
        action_panel.add(marker_size_label, constraints)
        action_panel.add(marker_size_combo, constraints)
        self.marker_size = marker_size_combo
        # Add "Marker Shape"
        marker_shape_label = JLabel("Marker Shape", JLabel.CENTER, enabled=False)
        marker_shape_combo = JComboBox(
            MARKER_SHAPES,
            enabled=False,
            selectedIndex=DEFAULT_SHAPE,
            itemStateChanged=self.update_markers)
        action_panel.add(marker_shape_label, constraints)
        action_panel.add(marker_shape_combo, constraints)
        self.marker_shape = marker_shape_combo
        # Add separator
        action_panel.add(JSeparator(), constraints)
        # Add "Counts Table" button
        counts_button = JButton(
            "Results",
            enabled=False,
            actionPerformed=self.counts_table)
        action_panel.add(counts_button, constraints)
        self.output_buttons.append(counts_button)
        # Add "Save Markers" button
        save_button = JButton(
            "Save Markers",
            enabled=False,
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
        self.add_syncytium()
        # Add panels to frame
        constraints = GridBagConstraints()
        self.getContentPane().setLayout(GridBagLayout())
        constraints.anchor = GridBagConstraints.NORTH
        self.getContentPane().add(scroll_pane, constraints)
        self.getContentPane().add(action_panel, constraints)
        # Add status line
        self.status_line = JTextField(enabled=False)
        constraints.gridy=1
        constraints.gridwidth=GridBagConstraints.REMAINDER
        constraints.fill=GridBagConstraints.HORIZONTAL
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
            ic = imp.getCanvas()
            for ml in ic.getMouseListeners():
                ic.removeMouseListener(ml)
            ic.addMouseListener(FusionClickListener(ic))
            imp.getWindow().addWindowListener(ImageClosingListener(self))
            imp.setRoi(self.syncytia.active_roi)
            imp.setOverlay(self.syncytia.overlay)
            self.imp = imp
            self.status_line.setText(imp.getTitle())
            self.update_markers()
            self.update_button_states()

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
            self.link_button.setEnabled(True)

    def hide_markers(self, event=None):
        if self.hide_box.isSelected():
            self.imp.deleteRoi()
            self.imp.setHideOverlay(True)
        else:
            self.imp.setRoi(self.syncytia.active_roi)
            self.imp.setHideOverlay(False)

    def hide_single_cells(self, event=None):
        if self.hide_single_box.isSelected():
            self.syncytia.overlay.remove(self.syncytia._single_cells)
        elif not self.syncytia.overlay.contains(self.syncytia._single_cells):
            self.syncytia.overlay.add(self.syncytia._single_cells)
        self.imp.getCanvas().repaintOverlay()

    def add_syncytium(self, event=None):
        if self.next_idx == 0:
            name = "Single Cells       "
        else:
            name = "Syncytium {}".format(self.next_idx-1)
        # Create GUI elements
        rb = JRadioButton(
            name,
            enabled=True,
            selected=True,
            actionCommand=str(self.next_idx),
            itemStateChanged=self.select_syncytium)
        label = JTextField("{}".format(0), enabled=False, editable=False)
        label.setHorizontalAlignment(JTextField.CENTER)
        self.syncytia_group.add(rb)
        self.syncytia_panel.add(rb)
        self.syncytia_panel.add(label)
        self.radio_buttons.append(rb)
        self.count_labels.append(label)
        # Update roi counter
        if self.next_idx > 0:
            rb.setSelected(True)
        self.next_idx += 1
        if self.next_idx == 1:
            return
        self.update_syncytia_panel()

    def update_syncytia_panel(self):
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
        counter_idx = int(self.syncytia_group.getSelection().getActionCommand())
        self.syncytia.set_syncytium(counter_idx)
        self.imp.setRoi(self.syncytia.active_roi)

    def clear_syncytium(self, event=None):
        IJ.showMessage("Not implemented")

    def clear_all_syncytia(self, event=None):
        if IJ.showMessageWithCancel("WARNING", "CLEAR ALL SYNCYTIA?"):
            self.syncytia.reset()
            self.remove_extra_counters()
            self.update_syncytia_panel()
            self.update_markers()
            self.select_syncytium()
            self.imp.setRoi(self.syncytia.active_roi)
            self.imp.setOverlay(self.syncytia.overlay)

    def update_markers(self, event=None):
        size = self.marker_size.getSelectedIndex()
        shape = self.marker_shape.getSelectedIndex()
        show_numbers = self.show_numbers.isSelected()
        IJ.run("Point Tool...", "size={} type={} show {}".format(
            MARKER_SIZES[size],
            MARKER_SHAPES[shape],
            "label" if show_numbers else ""))
        self.syncytia.set_markers(size, shape, show_numbers)
        self.imp.getCanvas().repaintOverlay()

    def load_markers(self, event=None):
        if (not self.syncytia.is_saved() and
            not IJ.showMessageWithCancel("WARNING", "THIS WILL CLEAR EXISTING MARKERS")):
            return
        filedialog = OpenDialog('Load Markers from json File', "")
        if filedialog.getPath():
            fpath = os.path.join(filedialog.getDirectory(),filedialog.getFileName())
            self.syncytia.from_json(fpath)
            self.remove_extra_counters()
            self.revalidate()
            self.imp.setRoi(self.syncytia.active_roi)
            self.imp.setOverlay(self.syncytia.overlay)
            self.select_syncytium()
            self.update_markers()
            self.hide_markers()
            self.hide_single_cells()

    def counts_table(self, event=None):
        table = self.syncytia.get_table()
        table.show("SyncytiaCount")

    def save_markers(self, event=None):
        if self.syncytia.is_empty():
            IJ.showMessage("There are no markers, Nothing to save")
            return
        fname = os.path.splitext(self.status_line.getText())[0]+'_markers'
        filedialog = SaveDialog('Select filename to save', fname, ".json")
        if filedialog.getFileName():
            fpath = filedialog.getDirectory()+filedialog.getFileName()
            self.syncytia.to_json(fpath)

    def update_counts(self):
        while self.next_idx < self.syncytia.syncytia_count:
            self.add_syncytium()
        self.count_labels[0].setText("{}".format(
            self.syncytia.get_nuclei_count(0)))
        for idx in range(1, self.next_idx):
            self.count_labels[idx].setText("{}".format(
                self.syncytia.get_nuclei_count(idx)))

    def run(self):
        if self.imp is not None:
            self.update_counts()

    def close(self, event=None):
        if (self.syncytia.is_saved() or IJ.showMessageWithCancel(
            "WARNING", "MARKERS ARE NOT SAVED! EXIT WITHOUT SAVING?")):
            self.scheduled_executor.shutdown()
            self.unlink_image()
            self.dispose()

    def unlink_image(self):
        if self.imp is not None and self.imp.isVisible():
            ic = self.imp.getCanvas()
            for ml in ic.getMouseListeners():
                if isinstance(ml, FusionClickListener):
                    ic.removeMouseListener(ml)
            ic.addMouseListener(ic)
            window = self.imp.getWindow()
            for wl in window.getWindowListeners():
                if isinstance(wl, ImageClosingListener):
                    window.removeWindowListener(wl)
        self.imp = None
        self.update_button_states()

    def remove_extra_counters(self):
        while self.next_idx > self.syncytia.syncytia_count:
            rb = self.radio_buttons.pop()
            label = self.count_labels.pop()
            self.syncytia_group.remove(rb)
            self.syncytia_panel.remove(rb)
            self.syncytia_panel.remove(label)
            self.next_idx -= 1
        self.radio_buttons[-1].setSelected(True)

if __name__ in ['__main__', '__builtin__']:
    SyncytiaCounter()
