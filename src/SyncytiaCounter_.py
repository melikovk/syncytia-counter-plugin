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

    def __init__(self):
        self._roi = [PointRoi(-10,-10)]
        self._saved = [roi.clone() for roi in self._roi]
        self._roi_idx = 0
        self._roi_limit = 10
        self._overlay = Overlay(self._roi[0])

    def getActiveRoi(self):
        return self._roi[self._roi_idx]

    def getOverlay(self):
        return self._overlay
        
    def setSyncytium(self, idx):
        q, r = divmod(idx, self._roi_limit)
        while q + 1 > len(self._roi):
            self.appendRoi()
        self._roi[q].setCounter(r)
        self._roi_idx = q

    def getSyncytiaNumber(self):
        num = ((len(self._roi) - 1) * self._roi_limit + 
               self._roi[-1].getLastCounter())
        return num

    def getNucleiCount(self, idx):
        q, r = divmod(idx, self._roi_limit)
        while q + 1 > len(self._roi):
            self.appendRoi()
        if r > 0:
            n = self._roi[q].getCount(r)
        else:
            n = self._roi[q].getCount(r) - 1
        return n

    def isSaved(self):
        if len(self._roi) != len(self._saved):
            return False
        for roi, saved in zip(self._roi, self._saved):
            if roi.getNCoordinates() != saved.getNCoordinates():
                return False
            points = roi.getContainedPoints()
            other_points = saved.getContainedPoints()
            for i in range(roi.getNCoordinates()):
                if (points[i] != other_points[i] or
                 roi.getCounter(i) != saved.getCounter(i)):
                    return False
        return True

    def appendRoi(self):
        roi = PointRoi(-10,-10)
        roi.setSize(self._roi[0].getSize())
        roi.setPointType(self._roi[0].getPointType())
        roi.setShowLabels(self._roi[0].getShowLabels())
        # IJ.run("Point Tool...", "".format())
        self._roi.append(roi)
        self._overlay.add(roi)

    def updateMarkers(self, markerSize, markerType, showLabels):
        for roi in self._roi:
            roi.setSize(markerSize)
            roi.setPointType(markerType)
            roi.setShowLabels(showLabels)

    def isEmpty(self):
        return all([roi.getNCoordinates() == 1 for roi in self._roi])

    def fromJSON(self, fpath):
        """Load markers from json file. Return None if file format is not 
        correct.
        """
        with open(fpath, 'r') as f:
            data = json.load(f)
        if data.get("format") != "markers":
            IJ.showDialog("Wrong format of the file!")
            return
        markerSize = self._roi[0].getSize()
        markerType = self._roi[0].getPointType()
        showLabels = self._roi[0].getShowLabels()
        self._roi = [PointRoi(-10,-10)]
        self._overlay = Overlay(self._roi[0])
        self.updateMarkers(markerSize, markerType, showLabels)
        for marker in data['data']:
            q, r = divmod(marker['idx'], self._roi_limit)
            while q + 1 > len(self._roi):
                self.appendRoi()
            self._roi[q].setCounter(r)
            self._roi[q].addPoint(*marker['position'])
        self._saved = [roi.clone() for roi in self._roi]
        
    def toJSON(self, fpath):
        """ Save markers to json file
        """
        indexes = []
        points = []
        for idx, roi in enumerate(self._roi):
            indexes += [self._roi_limit * idx + i & 255 
                            for i in roi.getCounters()[1:]]
            points += [(p.x, p.y) for p in roi.getContainedPoints()[1:]]
        syncytia = [{'idx': idx, 'position':p} 
                        for idx, p in zip(indexes, points)]
        with open(fpath, 'w') as f:
            json.dump({"format":"markers", "data":syncytia}, f)
        self._saved = [roi.clone() for roi in self._roi]

    def getTable(self):
        table = ResultsTable()
        max_idx = self.getSyncytiaNumber()
        count = self.getNucleiCount(0)
        table.addValue("Count", count)
        table.addLabel("Single cells")
        table.incrementCounter()
        for idx in range(1, max_idx + 1):
            count = self.getNucleiCount(idx)
            if count > 0:
                table.addValue("Count", count)
                table.addLabel("Syncytium {}".format(table.getCounter() - 1))
                table.incrementCounter()
        table.deleteRow(table.getCounter() - 1)
        return table

    def clearAll(self):
        self._roi = [PointRoi(-10, -10) for _ in self._roi]
        self._saved = [roi.clone() for roi in self._roi]
        self._overlay = Overlay()
        for roi in self._roi:
            self._overlay.add(roi)

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
        link_button = JButton("Link Image",
                              enabled=True,
                              actionPerformed=self.link_image)
        action_panel.add(link_button, constraints)
        self.link_button = link_button
        # Add separator
        action_panel.add(JSeparator(), constraints)
        # Add "Add Syncytium" Button
        add_button = JButton("Add Syncytium",
                             enabled=False,
                             actionPerformed=self.add_syncytium)
        action_panel.add(add_button, constraints)
        self.action_buttons.append(add_button)
        # Add "Clear this syncytium" button
        clearthis_button = JButton("Clear This Syncytium",
                                   enabled=False,
                                   actionPerformed=self.clear_syncytium)
        action_panel.add(clearthis_button, constraints)
        self.action_buttons.append(clearthis_button)
        # Add "Clear All" button
        clearall_button = JButton("Clear All",
                                  enabled=False,
                                  actionPerformed=self.clear_all_syncytia)
        action_panel.add(clearall_button, constraints)
        self.action_buttons.append(clearall_button)
        # Add "Load Markers" button
        load_button = JButton("Load Markers",
                              enabled=False,
                              actionPerformed=self.load_markers)
        action_panel.add(load_button, constraints)
        self.action_buttons.append(load_button)
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
        counts_button = JButton("Results",
                                enabled=False,
                                actionPerformed=self.counts_table)
        action_panel.add(counts_button, constraints)
        self.output_buttons.append(counts_button)
        # Add "Save Markers" button
        save_button = JButton("Save Markers",
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
        self.pack()
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
            imp.setRoi(self.syncytia.getActiveRoi())
            imp.setOverlay(self.syncytia.getOverlay())
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
            self.imp.setRoi(self.syncytia.getActiveRoi())
            self.imp.setHideOverlay(False)

    def add_syncytium(self, event=None):
        if self.next_idx == 0:
            name = "Single Cells       "
        else:
            name = "Syncytium {}".format(self.next_idx)
        # Create GUI elements
        rb = JRadioButton(name,
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
        size = self.scroll_pane.getPreferredSize()
        max_height = self.action_panel.getMinimumSize().height
        if size.height > max_height:
            size.height = max_height
            self.scroll_pane.setPreferredSize(size)
        self.revalidate()
        new_height = self.scroll_pane.getVerticalScrollBar().getMaximum()
        self.scroll_pane.getVerticalScrollBar().setValue(new_height)

    def select_syncytium(self, event=None):
        counter_idx = int(self.syncytia_group.getSelection().getActionCommand())
        self.syncytia.setSyncytium(counter_idx)
        self.imp.setRoi(self.syncytia.getActiveRoi())

    def clear_syncytium(self, event=None):
        IJ.showMessage("Not implemented")

    def clear_all_syncytia(self, event=None):
        if IJ.showMessageWithCancel("WARNING", "CLEAR ALL SYNCYTIA?"):
            self.syncytia.clearAll()
            self.update_markers()
            self.select_syncytium()
            self.imp.setRoi(self.syncytia.getActiveRoi())
            self.imp.setOverlay(self.syncytia.getOverlay())

    def update_markers(self, event=None):
        size = self.marker_size.getSelectedIndex()
        shape = self.marker_shape.getSelectedIndex()
        show_numbers = self.show_numbers.isSelected()
        IJ.run("Point Tool...", "size={} type={} show {}".format(
            MARKER_SIZES[size],
            MARKER_SHAPES[shape],
            "label" if show_numbers else ""))
        self.syncytia.updateMarkers(size, shape, show_numbers)
        self.imp.getCanvas().repaintOverlay()

    def load_markers(self, event=None):
        if (not self.syncytia.isSaved() and
            not IJ.showMessageWithCancel("WARNING", "THIS WILL CLEAR EXISTING MARKERS")):
            return
        filedialog = OpenDialog('Load Markers from json File', "")
        if filedialog.getPath():
            fpath = os.path.join(filedialog.getDirectory(),filedialog.getFileName())
            self.syncytia.fromJSON(fpath)
            self.imp.setRoi(self.syncytia.getActiveRoi())
            self.imp.setOverlay(self.syncytia.getOverlay())
            self.update_markers()

    def counts_table(self, event=None):
        table = self.syncytia.getTable()
        table.show("SyncytiaCount")

    def save_markers(self, event=None):
        if self.syncytia.isEmpty():
            IJ.showMessage("There are no markers, Nothing to save")
            return
        fname = os.path.splitext(self.status_line.getText())[0]+'_markers'
        filedialog = SaveDialog('Select filename to save', fname, ".json")
        if filedialog.getFileName():
            fpath = filedialog.getDirectory()+filedialog.getFileName()
            self.syncytia.toJSON(fpath)

    def update_counts(self):
        while self.next_idx < self.syncytia.getSyncytiaNumber()+1:
            self.add_syncytium()
        self.count_labels[0].setText("{}".format(
            self.syncytia.getNucleiCount(0)))
        for idx in range(1, self.next_idx):
            self.count_labels[idx].setText("{}".format(
                self.syncytia.getNucleiCount(idx)))

    def run(self):
        if self.imp is not None:
            self.update_counts()

    def close(self, event=None):
        if (self.syncytia.isSaved()
                or IJ.showMessageWithCancel(
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

if __name__ in ['__main__', '__builtin__']:
    SyncytiaCounter()
