# Syncytia Counter

Jython script for [ImageJ](https://imagej.net/) developed primarily for marking nuclei in multinucleated cells (syncitia). The user interface resembles the interface of [Cell Counter Plugin](https://imagej.net/plugins/cell-counter), but unlike it this script is just a GUI wrapper around Multi-point Roi.

## Installation

Copy [/src/SyncytiaCounter_.py](https://github.com/melikovk/syncytia-counter-plugin/blob/master/src/SyncytiaCounter_.py) file to Fiji.app/plugins/ folder  and restart ImageJ.

## Interface Controls

- **Link Image:** Link plugin to the current active image.
- **Load Markers:** Load markers from the file. *Note: Removes current markers.*
- **Add Syncytium:** Add counter for the new syncytium.
- **Clear This Syncytium:** Delete all marker for currently selected syncytium.
- **Clear All:** Clear all markers.
- **Show Numbers:** Check if you want to show syncytium index next to the marker. Single Cell markers are always assigned index 0.
- **Hide Markers:** Do not show markers on the image.
- **Hide Single Cells:** Do not show single cell markers on the image.
- **Marker Size:** Select marker size.
- **Marker Shape:** Select marker shape.
- **Results:** Show table with counts for all syncytia.
- **Save Markers:** Save markers to a file.

## Usage

The ***Link image***, ***Load Markers***, ***Results*** and ***Save Markers***  buttons are always active. Pressing the ***Link image*** button connects the plugin to the currently active image (title of the image window will appear in status line at the bottom of the plugin window) and activates the rest of the interface. Plugin can be relinked to another image. To add new marker choose the syncytia you want using corresponding radio-button and click on the position in the image. Markers for all syncytia can be manipulated in the same way  as in *Multi-point* roi tool: dragged around and deleted by holding down *ctrl* while clicking on the marker. Image view can be zoomed-in and moved around using *magnifier* and *hand* tools but Roi selection tools for the image are disabled. Do not change marker properties using toolbar since this is not synchronized with the plugin.

## File format

Markers are saved in the following json format:

```json
{
  'format':"markers",
  'data':[
     {
      'idx':idx1,
      'position':(x1,y1)
     },
     {
      'idx':idx2,
      'position':(x2,y2)
     },
     ...
  ]
}
```

Markers are saved in the order they were added.
