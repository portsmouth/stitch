Stitch is a Python script to assemble large Google maps. A rectangle of latitude and longitude is specified, together with a desired number of pixels along the long edge. The appropriate tiles are then automatically downloaded and stitched together into a single map.

You can enter latitude and longitude coordinates directly, or a web-based tool, which is provided in the download tarball as an html page, to convert a rectangle drawn in google maps into a text string code which can be copied and pasted into the GUI. Three map types are supported: satellite, hybrid (i.e. roads/boundaries overlaid on the satellite map), and terrain. The map dimensions are specified either as the number of pixels desired along the long edge of the rectangle (which will only be matched approximately by the stitched map, since no resampling is done), or alternatively by entering the zoom level of the Google tiles directly.

Note that Google may temporarily block your IP if you download too many tiles. To combat this, on restarting Stitch, the tiles already downloaded do not need to be downloaded again (provided the generated tiles/ directory is not deleted).

Ohloh link: https://www.ohloh.net/p/stitchmaps

The web based stitch tool (including the dynamically updated map URLS required to programmatically find the current locations of the Google map tiles) is shown below:

![http://stitch.googlecode.com/git/stitchtool.png](http://stitch.googlecode.com/git/stitchtool.png)



---



To run the app, you need to have [wxPython](http://www.wxpython.org) and the [Python Imaging Library (PIL)](http://www.pythonware.com/products/pil/) installed.

wxPython is available from:
http://www.wxpython.org/download.php#stable

To install PIL, it is easiest to do the following on the command line:
```
easy_install --find-links http://www.pythonware.com/products/pil/ Imaging
```