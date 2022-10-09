import os.path
import json
from copy import copy

from java.lang import Runnable, Cloneable
from java.util.concurrent import Executors, TimeUnit
from javax.swing import (JPanel, JFrame, JButton, JTextField, JCheckBox, JLabel,
                        SwingUtilities, BorderFactory, ButtonGroup, JComboBox,
      JRadioButton, JSeparator, SwingUtilities, WindowConstants)
from java.awt import GridBagLayout, GridBagConstraints, GridLayout, Insets
from java.awt.event import (MouseAdapter, ActionListener, ItemListener,
       WindowAdapter, ItemEvent)

from ij import WindowManager, IJ
from ij.gui import Toolbar, ImageCanvas, PointRoi
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

#
# Define Auxilary Classes
#

class SyncytiaRoi:
    """ Wrap PointRoi with additional methods
    """

    def __init__(self):
        self._roi = PointRoi(-10,-10)
        self._saved = self._roi.clone()
        self.imp = None

    def linkImage(self, imp):
        self.imp = imp
        self.imp.deleteRoi()
        self.imp.setRoi(self._roi)

    def setCounter(self, idx):
        self._roi.setCounter(idx)

    def getLastCounter(self):
        return self._roi.getLastCounter()

    def getCount(self, idx):
        return self._roi.getCount(idx)

    def isSaved(self):
        if self._roi.getNCoordinates() != self._saved.getNCoordinates():
            return False
        points = self._roi.getContainedPoints()
        other_points = self._saved.getContainedPoints()
        for i in range(self._roi.getNCoordinates()):
            if (points[i] != other_points[i] or
             self._roi.getCounter(i) != self._saved.getCounter(i)):
                return False
        return True

    def updateMarkers(self, markerSize, markerType, showLabels):
        self._roi.setSize(markerSize)
        self._roi.setPointType(markerType)
        self._roi.setShowLabels(showLabels)
        self.imp.getCanvas().repaintOverlay()

    def hideMarkers(self, hide):
        if hide:
            self.imp.deleteRoi()
        else:
            self.imp.setRoi(self._roi)

    def isEmpty(self):
        return self._roi.getNCoordinates() == 1

    def fromJSON(self, fpath):
        """Load markers from json file. Return None if file format is not 
        correct.
        """
        with open(fpath, 'r') as f:
            data = json.load(f)
        if data.get("format") != "markers":
            IJ.showDialog("Wrong format of the file!")
            return
        self._roi = PointRoi(-10,-10)
        for marker in data['data']:
            self._roi.setCounter(marker['idx'])
            self._roi.addPoint(self.imp, *marker['position'])
        self.imp.deleteRoi()
        self.imp.setRoi(self._roi)
        self._saved = self._roi.clone()

    def toJSON(self, fpath):
        """ Save markers to json file
        """
        indexes = [i & 255 for i in self._roi.getCounters()]
        points = [(p.x, p.y) for p in self._roi.getContainedPoints()]
        syncytia_list = []
        for i in range(1, len(indexes)):
            syncytia_list.append({'idx':indexes[i], 'position':points[i]})
        with open(fpath, 'w') as f:
            json.dump({"format":"markers", "data":syncytia_list}, f)
        self._saved = self._roi.clone()

    def getTable(self):
        table = ResultsTable()
        max_idx = self._roi.getLastCounter()
        count = self._roi.getCount(0) - 1
        table.addValue("Count", count)
        table.addLabel("Single cells")
        table.incrementCounter()
        for idx in range(1, max_idx + 1):
            count = self._roi.getCount(idx)
            if count > 0:
                table.addValue("Count", count)
                table.addLabel("Syncytium {}".format(table.getCounter() - 1))
                table.incrementCounter()
        table.deleteRow(table.getCounter() - 1)
        return table

    def clearAll(self):
        self._roi = PointRoi(-10, -10)
        self._saved = self._roi.clone()
        self.imp.deleteRoi()
        self.imp.setRoi(self._roi)

class ImageClosingListener(WindowAdapter):
    def __init__(self, parent):
        self.parent = parent

    def windowClosed(self, event):
        self.parent.unlink_image()

class FusionClickListener(MouseAdapter):
    def __init__(self, ic, parent):
        super(FusionClickListener, self).__init__()
        self.ic = ic
        self.parent = parent

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
        # self.filepath = None
        self.syncytia_list = SyncytiaRoi()
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
        # Add "Single cell" radiobutton and label
        self.add_syncytium()
        # Add panels to frame
        constraints = GridBagConstraints()
        self.getContentPane().setLayout(GridBagLayout())
        constraints.anchor = GridBagConstraints.NORTH
        self.getContentPane().add(syncytia_panel, constraints)
        self.getContentPane().add(action_panel, constraints)
        # Add status line
        self.status_line = JTextField(enabled=False)
        constraints.gridy=1
        constraints.gridwidth=GridBagConstraints.REMAINDER
        constraints.fill=GridBagConstraints.HORIZONTAL
        self.getContentPane().add(self.status_line, constraints)
        self.pack()
        self.setLocation(1000, 200)
        self.setVisible(True)

    def link_image(self, event=None):
        imp = WindowManager.getCurrentImage()
        if imp is None:
            IJ.noImage()
        elif self.syncytia_list.imp != imp:
            # Replace MouseListener
            ic = imp.getCanvas()
            for ml in ic.getMouseListeners():
                ic.removeMouseListener(ml)
            ic.addMouseListener(FusionClickListener(ic, self))
            imp.getWindow().addWindowListener(ImageClosingListener(self))
            self.status_line.setText(imp.getTitle())
            self.syncytia_list.linkImage(imp)
            self.update_markers()
            self.update_button_states()
        else:
            IJ.showMessage("The image '{}' is already linked".format(imp.getTitle()))

    def update_button_states(self):
        if self.syncytia_list.imp is not None:
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
        self.syncytia_list.hideMarkers(self.hide_box.isSelected())

    def add_syncytium(self, event=None):
        if self.next_idx == 0:
            name = "Single Cells"
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
        self.pack()

    def select_syncytium(self, event=None):
        counter_idx = int(self.syncytia_group.getSelection().getActionCommand())
        self.syncytia_list.setCounter(counter_idx)

    def clear_syncytium(self, event=None):
        IJ.showMessage("Not implemented")

    def clear_all_syncytia(self, event=None):
        if IJ.showMessageWithCancel("WARNING", "CLEAR ALL SYNCYTIA?"):
            self.syncytia_list.clearAll()
            self.update_markers()
            self.select_syncytium()

    def update_markers(self, event=None):
        self.syncytia_list.updateMarkers(self.marker_size.getSelectedIndex(),
                                         self.marker_shape.getSelectedIndex(),
                                         self.show_numbers.isSelected())

    def load_markers(self, event=None):
        if (not self.syncytia_list.isSaved() and
            not IJ.showMessageWithCancel("WARNING", "THIS WILL CLEAR EXISTING MARKERS")):
            return
        filedialog = OpenDialog('Load Markers from json File', "")
        if filedialog.getPath():
            fpath = os.path.join(filedialog.getDirectory(),filedialog.getFileName())
            self.syncytia_list.fromJSON(fpath)
            self.update_markers()

    def counts_table(self, event=None):
        table = self.syncytia_list.getTable()
        table.show("SyncytiaCount")

    def save_markers(self, event=None):
        if self.syncytia_list.isEmpty():
            IJ.showMessage("There are no markers, Nothing to save")
            return
        fname = os.path.splitext(self.status_line.getText())[0]+'_markers'
        filedialog = SaveDialog('Select filename to save', fname, ".json")
        if filedialog.getFileName():
            fpath = filedialog.getDirectory()+filedialog.getFileName()
            self.syncytia_list.toJSON(fpath)

    def update_counts(self):
        while self.next_idx < self.syncytia_list.getLastCounter()+1:
            self.add_syncytium()
        syncytia = self.syncytia_list
        self.count_labels[0].setText("{}".format(syncytia.getCount(0)-1))
        for idx in range(1, self.next_idx):
            self.count_labels[idx].setText("{}".format(syncytia.getCount(idx)))

    def run(self):
        if self.syncytia_list.imp is not None:
            self.update_counts()

    def close(self, event=None):
        if (self.syncytia_list.isSaved()
                or IJ.showMessageWithCancel(
                    "WARNING", "MARKERS ARE NOT SAVED! EXIT WITHOUT SAVING?")):
            self.scheduled_executor.shutdown()
            if self.syncytia_list.imp is not None:
                ic = self.syncytia_list.imp.getCanvas()
                for ml in ic.getMouseListeners():
                    if isinstance(ml, FusionClickListener):
                        ic.removeMouseListener(ml)
                ic.addMouseListener(ic)
                window = self.syncytia_list.imp.getWindow()
                for wl in window.getWindowListeners():
                    if isinstance(wl, ImageClosingListener):
                        window.removeWindowListener(wl)
            self.dispose()

    def unlink_image(self):
        print('OK')
        self.syncytia_list.imp = None
        self.update_button_states()

if __name__ in ['__main__', '__builtin__']:
    SyncytiaCounter()
