from javax.swing import (JPanel, JFrame, JTable, JScrollPane, JButton, JTextField, JCheckBox,
                        JTextArea, ListSelectionModel, SwingUtilities, JLabel, BorderFactory,
                        ButtonGroup, JRadioButton, JComboBox, JSeparator)
from java.awt import GridBagLayout, GridBagConstraints, GridLayout, Dimension, Font, Insets, Color, Cursor
from java.awt.event import (KeyAdapter, MouseListener, MouseAdapter, KeyEvent, ActionListener,
							WindowAdapter, ItemEvent, ItemListener, WindowStateListener)
from ij.plugin import PlugIn
from ij import WindowManager, IJ, ImageListener
from ij.gui import Toolbar, ImageCanvas, ImageWindow, StackWindow, PointRoi, Overlay, GenericDialog
from java.awt.geom import Point2D
from java.lang import Runnable
from java.util.concurrent import Executors, TimeUnit  
from javax.swing import WindowConstants
from javax.swing import SwingUtilities
from ij.measure import ResultsTable
from ij.io import SaveDialog, OpenDialog
import os.path
import sys
import json

MARKER_SIZES = ["Tiny", "Small", "Medium", "Large", "XL", "XXL", "XXXL"]
MARKER_SHAPES = ["Hybrid", "Cross", "Dot", "Circle"]
DEFAULT_SHOW_NUMBERS = True
DEFAULT_SIZE = 2
DEFAULT_SHAPE = PointRoi.DOT
	
class CleanupOnClose(WindowAdapter):
	def __init__(self, frame):
		self.frame = frame

	def windowClosing(self, event):
		self.frame.destroy()		

class SyncytiaCounter(PlugIn, JFrame, Runnable):
	def __init__(self):
		super(JFrame, self).__init__("Syncytia Counter")
		self.imp = None
		self.filepath = None
		self.syncytia_list = None
		self.saved_syncytia = None
		self.next_idx = 0
		self.count_labels = []
		self.radio_buttons = []
		self.action_buttons = []
		self.output_buttons = []
		self.action_listener = ClickButtonListener()
		self.item_listener = SyncytiaCounterItemListener()
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
		link_button = JButton("Link Image", enabled=True)  
		self.action_listener.register_component_handler(link_button, self.link_image)
		action_panel.add(link_button, constraints)
		self.link_button = link_button
		# Add separator
		action_panel.add(JSeparator(), constraints)
		# Add "Add Syncytium" Button		
		add_button = JButton("Add Syncytium", enabled=False)
		self.action_listener.register_component_handler(add_button, self.add_syncytium)
		action_panel.add(add_button, constraints)
		self.action_buttons.append(add_button)
		# Add "Clear this syncytium" button
		clearthis_button = JButton("Clear This Syncytium", enabled=False)  
		self.action_listener.register_component_handler(clearthis_button, self.clear_syncytium)  
		action_panel.add(clearthis_button, constraints)
		self.action_buttons.append(clearthis_button)
		# Add "Clear All" button
		clearall_button = JButton("Clear All", enabled=False)  
		self.action_listener.register_component_handler(clearall_button, self.clear_all_syncytia)
		action_panel.add(clearall_button, constraints)
		self.action_buttons.append(clearall_button)
		# Add "Load Markers" button
		load_button = JButton("Load Markers", enabled=False)  
		self.action_listener.register_component_handler(load_button, self.load_markers)
		action_panel.add(load_button, constraints)
		self.action_buttons.append(load_button)
		# Add separator
		action_panel.add(JSeparator(), constraints)								
		# Add "Show Numbers" checkbox
		show_numbers_box = JCheckBox("Show Numbers", selected=True, enabled=False)  
		self.item_listener.register_component_handler(show_numbers_box, self.update_show_numbers)  
		action_panel.add(show_numbers_box, constraints)
		self.show_numbers = show_numbers_box
		# Add "Hide Markers" checkbox
		hide_box = JCheckBox("Hide Markers", selected=False, enabled=False)  
		self.item_listener.register_component_handler(hide_box, self.hide_markers)  
		action_panel.add(hide_box, constraints)
		self.hide_box = hide_box
		# Add "Marker Size"
		marker_size_label = JLabel("Marker Size", JLabel.CENTER, enabled=False)
		marker_size_combo = JComboBox(MARKER_SIZES, enabled=False, selectedIndex = DEFAULT_SIZE)
		self.item_listener.register_component_handler(marker_size_combo, self.update_marker_size)
		action_panel.add(marker_size_label, constraints)
		action_panel.add(marker_size_combo, constraints)
		self.marker_size = marker_size_combo
		# Add "Marker Shape"
		marker_shape_label = JLabel("Marker Shape", JLabel.CENTER, enabled=False)
		marker_shape_combo = JComboBox(MARKER_SHAPES, enabled=False, selectedIndex = DEFAULT_SHAPE)
		self.item_listener.register_component_handler(marker_shape_combo, self.update_marker_shape)
		action_panel.add(marker_shape_label, constraints)
		action_panel.add(marker_shape_combo, constraints)
		self.marker_shape = marker_shape_combo
		# Add separator
		action_panel.add(JSeparator(), constraints)						
		# Add "Counts Table" button
		counts_button = JButton("Results", enabled=False)  
		self.action_listener.register_component_handler(counts_button, self.counts_table)
		action_panel.add(counts_button, constraints)
		self.output_buttons.append(counts_button)
		# Add "Save Markers" button
		save_button = JButton("Save Markers", enabled=False)  
		self.action_listener.register_component_handler(save_button, self.save_markers)
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
		self.init_syncytium()
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
		self.addWindowListener(CleanupOnClose(self))
		self.setVisible(True)
		
	def link_image(self, event=None):
		imp = WindowManager.getCurrentImage()
		if imp is None:
			IJ.noImage()
		elif self.imp != imp:
			# Replace MouseListener
			ic = imp.getCanvas()
			for ml in ic.getMouseListeners():
				ic.removeMouseListener(ml)
			ic.addMouseListener(FusionClickListener(ic, self))
			imp.getWindow().addWindowListener(ImageClosingListener(self))
			self.imp = imp
			self.status_line.setText(imp.getTitle())
			self.update_button_states()
			self.set_roi(PointRoi(-10,-10))
			fileinfo = imp.getOriginalFileInfo()
			if fileinfo is not None:
				self.filepath = os.path.join(fileinfo.directory, fileinfo.fileName)
		else:
			IJ.showMessage("The image '{}' is already linked".format(imp.getTitle()))
			
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

	def init_syncytium(self):
		idx = self.next_idx
		rb = JRadioButton("Single Cells", enabled=False, selected=True)
		rb.setActionCommand(str(idx))
		self.item_listener.register_component_handler(rb, self.select_syncytium)  
		label = JTextField("{}".format(0), enabled=False, editable=False)
		label.setHorizontalAlignment(JTextField.CENTER)
		self.syncytia_group.add(rb)
		self.syncytia_panel.add(rb)
		self.syncytia_panel.add(label)
		self.radio_buttons.append(rb)
		self.count_labels.append(label)
		self.next_idx += 1
								
	def hide_markers(self, event=None):
		if self.hide_box.isSelected():
			self.imp.deleteRoi()
		else:
			self.imp.setRoi(self.syncytia_list)
	
	def add_syncytium(self, event=None):
		idx = self.next_idx
		name = "Syncytium {}".format(idx)
		# Create GUI elements
		rb = JRadioButton(name, enabled=True)
		rb.setActionCommand(str(idx))
		self.item_listener.register_component_handler(rb, self.select_syncytium)  
		label = JTextField("{}".format(0), enabled=False, editable=False)
		label.setHorizontalAlignment(JTextField.CENTER)
		self.syncytia_group.add(rb)
		self.syncytia_panel.add(rb)
		self.syncytia_panel.add(label)
		self.radio_buttons.append(rb)
		self.count_labels.append(label)
		# Update roi counter
		rb.setSelected(True)
		self.next_idx += 1
		self.pack()
		
	def select_syncytium(self, event=None):
		if event is None:
			counter_idx = int(self.syncytia_group.getSelection().getActionCommand())
			self.syncytia_list.setCounter(counter_idx)
		elif event.getStateChange() == ItemEvent.SELECTED:
			counter_idx = int(event.getItem().getActionCommand())
			self.syncytia_list.setCounter(counter_idx)
		
	def clear_syncytium(self, event=None):
		print("Remove Syncytium")
		
	def set_roi(self, roi):
		self.imp.deleteRoi()
		self.imp.setRoi(roi)
		roi.setSize(self.marker_size.getSelectedIndex())
		roi.setPointType(self.marker_shape.getSelectedIndex())
		roi.setShowLabels(self.show_numbers.isSelected())
		self.syncytia_list = roi
		for idx in range(self.next_idx, roi.getLastCounter()+1):
			self.add_syncytium()
		self.select_syncytium()
	
	def clear_all_syncytia(self, event=None):
		if IJ.showMessageWithCancel("WARNING", "CLEAR ALL SYNCYTIA?"):
			self.set_roi(PointRoi(-10,-10))
			self.select_syncytium()
		
	def update_show_numbers(self, event=None):
		self.syncytia_list.setShowLabels(self.show_numbers.isSelected())
		self.imp.getCanvas().repaintOverlay()
		
	def update_marker_size(self, event=None):
		self.syncytia_list.setSize(self.marker_size.getSelectedIndex())
		self.imp.getCanvas().repaintOverlay()
		
	def update_marker_shape(self, event=None):
		self.syncytia_list.setPointType(self.marker_shape.getSelectedIndex())
		self.imp.getCanvas().repaintOverlay()
	
	def load_markers(self, event=None):
		if (self.syncytia_list.getNCoordinates() > 1 and
			not IJ.showMessageWithCancel("WARNING", "THIS WILL CLEAR EXISTING MARKERS")):
				return
		filedialog = OpenDialog('Load Markers from json File', "")
		if filedialog.getPath():
			fpath = os.path.join(filedialog.getDirectory(),filedialog.getFileName())
			with open(fpath, 'r') as f:
				data = json.load(f)
			if data.get("format") != "markers":
				IJ.showDialog("Wrong format of the file!")
				return
			syncytia_list = PointRoi(-10,-10)
			for point in data['data']:
				syncytia_list.setCounter(point['idx'])
				syncytia_list.addPoint(*point['position'])
			self.set_roi(syncytia_list)
		
	def counts_table(self, event=None):
		table = ResultsTable()
		max_idx = self.syncytia_list.getLastCounter()
		count = self.syncytia_list.getCount(0) - 1
		table.addValue("Count", count)
		table.addLabel("Single cells")
		table.incrementCounter()
		for idx in range(1, max_idx + 1):
			count = self.syncytia_list.getCount(idx)
			if count > 0:
				table.addValue("Count", count)
				table.addLabel("Syncytium {}".format(table.getCounter() - 1))
				table.incrementCounter()
		table.deleteRow(table.getCounter() - 1)
		table.show("SyncytiaCount")
		print(self.saved_syncytia.getNCoordinates(), self.syncytia_list.getNCoordinates())
		print(compare_PointRoi(self.saved_syncytia, self.syncytia_list))
		print(self.saved_syncytia == self.syncytia_list)
		
	def save_markers(self, event=None):
		if self.syncytia_list.getNCoordinates() == 1:
			IJ.showMessage("There are no markers, Nothing to save")
			return
		fname = os.path.splitext(self.status_line.getText())[0]+'_markers'
		filedialog = SaveDialog('Select filename to save', fname, ".json")
		if filedialog.getFileName():
			indexes = [i & 255 for i in self.syncytia_list.getCounters()]
			points = [(p.x, p.y) for p in self.syncytia_list.getContainedPoints()]
			syncytia_list = []
			for i in range(1, len(indexes)):
				syncytia_list.append({'idx':indexes[i], 'position':points[i]})
			with open(filedialog.getDirectory()+filedialog.getFileName(), 'w') as f:
					json.dump({"format":"markers", "data":syncytia_list}, f)
		self.saved_syncytia = self.syncytia_list.clone()
	
	def update_counts(self):
		syncytia = self.syncytia_list
		self.count_labels[0].setText("{}".format(syncytia.getCount(0)-1))
		for idx in range(1, self.next_idx):
			self.count_labels[idx].setText("{}".format(syncytia.getCount(idx)))
				
	def run(self):
		if self.imp is not None:
			self.update_counts()
		
	def destroy(self):
		self.scheduled_executor.shutdown()  
		
	def unlink_image(self):
		self.imp = None
		self.update_button_states()

def compare_PointRoi(x, y):
	if x.getNCoordinates() != y.getNCoordinates():
		return False
	xpoints = x.getContainedPoints()
	ypoints = y.getContainedPoints()
	for i in range(x.getNCoordinates()):
		if (xpoints[i] != ypoints[i] or
			x.getCounter(i) != y.getCounter(i)):
			return False
	return True

PointRoi.__eq__ = compare_PointRoi

						
class ClickButtonListener(ActionListener):
	def __init__(self):
		self.actions = {}
		
	def actionPerformed(self, event):
		self.actions[event.getSource()](event)
		
	def register_component_handler(self, component, handler):
		component.addActionListener(self)
		self.actions[component] = handler
		
class SyncytiaCounterItemListener(ItemListener):
	def __init__(self):
		self.actions = {}
		
	def itemStateChanged(self, event):
		self.actions[event.getSource()](event)
		
	def register_component_handler(self, component, handler):
		component.addItemListener(self)
		self.actions[component] = handler
									
class FusionClickListener(MouseAdapter):
	def __init__(self, ic, parent):
		super(FusionClickListener, self).__init__()
		self.ic = ic
		self.parent = parent

	def mouseClicked(self, event):
		ImageCanvas.mouseClicked(self.ic, event)
	
	def mouseEntered(self, event):
		if (IJ.spaceBarDown() or Toolbar.getToolId() == Toolbar.MAGNIFIER  or Toolbar.getToolId() == Toolbar.HAND):
			ImageCanvas.mouseEntered(self.ic, event)
		else:
			Toolbar.getInstance().setTool("multipoint")
			if self.parent.imp.getRoi() is None:
				self.parent.imp.setRoi(self.parent.syncytia_list)
				self.parent.hide_box.setSelected(False)
			ImageCanvas.mouseEntered(self.ic, event)
	
	def mouseExited(self, event):
		ImageCanvas.mouseExited(self.ic, event)
		
	def mousePressed(self, event):
		ImageCanvas.mousePressed(self.ic, event)
		
	def mouseReleased(self, event):
		ImageCanvas.mouseReleased(self.ic, event)
		
class ImageClosingListener(WindowAdapter):
	def __init__(self, parent):
		self.parent = parent
		
	def windowClosed(self, event):
		self.parent.unlink_image()

if __name__ in ['__main__', '__builtin__']:
	SyncytiaCounter()
