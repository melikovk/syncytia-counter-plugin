import glob
import json

from javax.swing import JFrame, JButton, JLabel, WindowConstants
from java.awt import FlowLayout, Font

from ij.io import DirectoryChooser
from ij.measure import ResultsTable

class SyncytiaSummary(JFrame):
    """ 
    Generates a summary of syncytia in the given folder

    """

    def __init__(self):
        super(JFrame, self).__init__("Syncytia Counter")
        self.label = JLabel("Select Folder to Process",
                                    JLabel.CENTER,
                                    enabled=True)
        font = self.label.getFont()
        font_size = 18
        self.label.setFont(Font(font.name, font.style, font_size))    
        self.button = JButton("Select Folder",
                              enabled=True,
                              actionPerformed=self.summarize)
        font = self.button.getFont()
        self.button.setFont(Font(font.name, font.style, font_size))
        self.getContentPane().setLayout(FlowLayout())
        self.getContentPane().add(self.label)
        self.getContentPane().add(self.button)
        self.pack()
        self.setLocation(1000, 200)
        self.setMinimumSize(self.getSize())
        self.setVisible(True)
    
    def summarize(self, event):
        folderdialog = DirectoryChooser("Select Folder")
        folder = folderdialog.getDirectory()
        if folder:
            files = glob.glob(folder+"*_markers.json")
            hist = {1:0}
            for file in files:
                with open(file, 'r') as f:
                    data = json.load(f)
                syncytia = {}
                if data['format'] != 'markers':
                    continue
                # Collect nuclei into syncytia
                for nuc in data['data']:
                    nuc_idx = nuc['idx']
                    syncytia[nuc_idx] = syncytia.setdefault(nuc_idx, 0) + 1
                # Add single cells
                hist[1] = hist[1] + syncytia.pop(0,0)
                for val in syncytia.values():
                    hist[val] = hist.setdefault(val, 0) + 1
            max_size = max(hist.keys())
            nuclei = list(range(1, max_size+1))
            counts = [hist.setdefault(i+1, 0) for i in range(max_size)]
            long_summary = ResultsTable(max_size)
            long_summary.setValues('nuclei', nuclei)
            long_summary.setValues('counts', counts)
            long_summary.show('Histogram')
            short_summary = ResultsTable()
            short_summary.addValue("Count", counts[0])
            short_summary.addLabel("Single cells")
            short_summary.incrementCounter()
            short_summary.addValue("Count", 
                sum([(i+1)*n for i, n in enumerate(counts)]) - counts[0])
            short_summary.addLabel("Nuclei in syncytia")
            short_summary.incrementCounter()
            short_summary.addValue("Count", 
                sum([(i)*n for i, n in enumerate(counts)]))
            short_summary.addLabel("Fusion index")
            short_summary.show("Short summary")
            
       

if __name__ in ['__main__', '__builtin__']:
    SyncytiaSummary()