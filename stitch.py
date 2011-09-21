#! /bin/env python

###################################################################################
#                                                                                 #
#  Stitch v3.0,                                                                   #
#  http://www.jportsmouth.com/code/Stitch/stitch.html                             #
#  Copyright (C) 2009-2010 Jamie Portsmouth (jamports@mac.com)                    #
#  Multithreading contributed by Morgan Tørvolt (morgan@torvolt.com)              #
#                                                                                 #
#  Stitch is a Python script to assemble large Google maps. A rectangle of        #
#  latitude and longitude is specified, together with a desired number of pixels  #
#  along the long edge. The appropriate tiles are then automatically downloaded   #
#  and stitched together into a single map.                                       #
#                                                                                 #
#  This program is free software: you can redistribute it and/or modify           #             
#  it under the terms of the GNU General Public License as published by           #
#  the Free Software Foundation, either version 3 of the License, or              #
#  (at your option) any later version.                                            #
#                                                                                 #
#  This program is distributed in the hope that it will be useful,                #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of                 #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                  #
#  GNU General Public License for more details.                                   #
#                                                                                 #
#  You should have received a copy of the GNU General Public License              #
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.          #
#                                                                                 #
###################################################################################

import sys
import os
import urllib
import urllib2
import math
import wx
import wx.html
import threading
import Queue

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFilter
from PIL import ImageMath


#########################################################################################################
# Current Google map URLS
# If the script reports that map URLS are invalid, replace the code section below
# with the updated version from http://www.jportsmouth.com/code/Stitch/stitch.html
#####################  start of map URL code section  ###################################################


NRM_URL = "http://mt0.google.com/vt/lyrs=m@118&hl=en&src=api&x=0&y=0&z=0&s="
SAT_URL = "http://khm0.google.com/kh/v=54&cookie=fzwq1C7TB0nUYgDs9ekB-1G3k3HolraYN4ITsQ&x=0&y=0&z=0&s="
PHY_URL = "http://mt0.google.com/vt/v=app.118&hl=en&src=api&x=0&y=0&z=0&s="
SKY_URL = "http://mw1.google.com/mw-planetary/sky/skytiles_v1/0_0_0.jpg"


######################  end of map URL code section  ####################################################


# Queue. We drop all the urls in this queue
grabPool = Queue.Queue( 0 )

# Background threads. We start a few of these
class ThreadingClass( threading.Thread ):

    def __init__(self):
        
        self._stopevent = threading.Event()
        threading.Thread.__init__(self)

    def join(self, timeout=None):

        self._stopevent.set()
        threading.Thread.join(self, timeout)

    def run( self ):

        self.serverSelectCounter = 0

        # Run until termination event. After filling the queue, we can just wait until the queue is empty.
        while not self._stopevent.isSet():

            try:
                tile = grabPool.get(True, 0.001)
            except:
                continue
                
            url = tile[0]
            output = './tiles/tile_' + tile[1] + '.jpg'
            
            # Fixing up url for servers that had %s writted into them for load balancing
            gotTile = False
            if( url.find( "%s" ) != -1 ):
                for x in range(4):
                    url = url % ( self.serverSelectCounter % 4 )
                    self.serverSelectCounter = self.serverSelectCounter + 1
                    gotTile = self.download(url, output)
                    if gotTile: break
                    
            # Otherwise url does not need to be fixed up
            else:    
                gotTile = self.download(url, output)
                
            if (gotTile != True):
                print "(Map URL " + url + " might be invalid or a server might be down. Visit http://www.jportsmouth.com/code/Stitch/stitch.html and update the map URL code section)"                
                
            grabPool.task_done()

    def download( self, url, output ):

         try:
            urllib.urlretrieve( url, output )
            return True
         except:
            return False



class StitchedMap:

    def __init__(self, lat, lon, res, zoom, maptype):

        self.lat = lat
        self.lon = lon
        self.latVal = (float(lat[0]), float(lat[1]))
        self.lonVal = (float(lon[0]), float(lon[1]))

        if (self.latVal[0] >= self.latVal[1]):
            print 'Invalid latitude range. Aborting.'
            return

        if (self.lonVal[0] >= self.lonVal[1]):
            print 'Invalid longitude range. Aborting.'
            return
        
        self.res = res
        self.zoom = zoom  # understood to be -1 if resolution specified
        self.maptype = maptype

        self.MAP_MODE_PREFIX = self.makeDummyUrl(NRM_URL.split('&')[0])
        self.SAT_MODE_PREFIX = self.makeDummyUrl(SAT_URL.split('&')[0])
        self.PHY_MODE_PREFIX = self.makeDummyUrl(PHY_URL.split('&')[0])
        self.SKY_MODE_PREFIX = SKY_URL.replace('0_0_0.jpg','')


    def makeDummyUrl(self, url):

        # Some string hacking to replace e.g. "http://mt0.google.com..." with "http://mt%s.google.com..."
        # so that later we can replace %s with an integer 0-4 for load balancing
        server_url = url.split(".google")
        server_name = server_url[0][0:len(server_url[0])-1]
        dummy_url = server_name + "%s.google" + server_url[1]
        return dummy_url

        
    def generate(self):
   
        c0 = "(" + self.lat[0] + ", " + self.lon[0] + ")"
        c1 = "(" + self.lat[1] + ", " + self.lon[1] + ")"

        print '\n######################################################################'
        print "Making " + self.maptype + " map defined by (lat, lon) corners " + c0 + " and " + c1

        EX = math.fabs(float(self.lon[1]) - float(self.lon[0]))
        EY = math.fabs(float(self.lat[1]) - float(self.lat[0]))
        print 'Requested map (lng, lat) size in degrees is: ', str(EX), str(EY)

        # compute which 256x256 tiles we need to download
        self.computeTileMatrix()

        if (self.zoom<0) or (self.zoom>19):
            print 'Invalid zoom level (' + str(self.zoom) + '). Aborting.'
            return
        print 'Zoom level: ', str(self.zoom)

        # Connect to Google maps and download tiles
        self.download()

        # Finally stitch the downloaded maps together into the final big map
        self.stitch()

       
    def computeTileRange(self):

        if self.zoom == -1:
            
            # find a zoom level which gives approximately the desired number of pixels along the long edge
            EX = math.fabs(float(self.lon[1]) - float(self.lon[0]))
            EY = math.fabs(float(self.lat[1]) - float(self.lat[0]))
            aspect = 2.0*EY/EX
            
            ntiles_x = 0
            ntiles_y = 0
            if (EX>EY):
                self.ntiles_x = long( float(self.res)/256 + 1 )
                self.ntiles_y = long( aspect*float(self.res)/256 + 1 )
            else:
                self.ntiles_y = long( float(self.res)/256 + 1 )
                self.ntiles_x = long( float(self.res)/(aspect*256) + 1 )
            
            log2of10 = 3.321928094887362
            self.zoom = log2of10 * math.log10( max(self.ntiles_x, self.ntiles_y) * 360.0/max(EX, EY) )

        self.zoom = long(self.zoom)

        # In satellite mode, the zoom level in the html query goes from 0 to 14 inclusive,
        # 0 being the lowest res (i.e. the map of the world).
        # In the other modes, the zoom level goes from -2 to 17 inclusive, 17 being the map of the world.
        if (self.maptype != 'satellite'):
            self.htmlzoom = 17 - self.zoom
            
        # Google maps uses the Mercator projection, so we need to convert the given latitudes 
        # into Mercator y-coordinates. Google takes the vertical edges of the map to be at
        # y = +/-pi, corresponding to latitude +/-85.051128.
        # It is convenient therefore to compute y/2 for each latitude. We can then
        # just use the y coord as if it were a latitude, with the top edges at +/-90.0 "degrees".
        l0 = self.latVal[0]
        l1 = self.latVal[1]
        self.yVal = (self.latitudeToMercator(l0), self.latitudeToMercator(l1))
            
        # get the corner tile 
        tileA = self.getTile(self.lonVal[0], self.yVal[0])
        tileB = self.getTile(self.lonVal[1], self.yVal[1])

        return [tileA, tileB]

        
    # Allow phi in range [-90.0, 90.0], return in same range
    def latitudeToMercator(self, phi):

         # If the given latitude falls outside of the +/-85.051128 range, we clamp it back into range.
        phimax = 85.05112
        if   phi>phimax: phi = phimax
        elif phi<-phimax: phi = -phimax
     
        # find sign    
        sign = 0.0
        if phi>=0.0: sign = 1.0
        else:        sign = -1.0
        
        # convert to rad
        phi *= math.pi/180.0

        # make positive for Mercator formula
        phi = math.fabs(phi)
        
        # find [0,pi] range Mercator coords
        y = math.log( math.tan(phi) + 1.0/math.cos(phi) )
        
        # put back sign and scale by factor of 2
        y *= 0.5*sign

        # convert to degrees
        y *= 180.0/math.pi

        # clamp to [-90.0, 90.0]
        if   y>90.0: y = 90.0
        elif y<-90.0: y = -90.0
        
        return y

        
    def computeTileMatrix(self):

        tileRange = self.computeTileRange()

        tileA = tileRange[0]
        tileB = tileRange[1]

        tileAstr = '(' + str(tileA[0]) + ',' + str(tileA[1]) + ')'
        tileBstr = '(' + str(tileB[0]) + ',' + str(tileB[1]) + ')'
        print 'Corner tile indices: ' + tileAstr + ', ' + tileBstr
        
        self.nX = abs(tileB[0] - tileA[0]) + 1
        self.nY = abs(tileB[1] - tileA[1]) + 1

        print 'Total number of tiles to download: ' + str(self.nX*self.nY)

        # Make a nX*nY matrix of the tiles (i,j) we need, with (0,0) in the lower-left.
        # The google tile indices (lng, lat) corresponding to (i,j) (at the given zoom level) are stored
        # in each tile.
        
        # We need the fact that in satellite mode, the lng, lat tile indices increase with both longitude
        # and latitude, but in the other modes, the lat index decreases with latitude
        self.tiles = []
        for i in range(0, self.nX):

            lng = tileA[0] + i
            column = []

            for j in range(0, self.nY):

                lat = 0
                if self.maptype == 'satellite':
                    lat = tileA[1] + j
                    code = self.genSatelliteTileCode(lng, lat)
                else:
                    lat = tileA[1] - j 
                    code = ''

                status = True
                tile = [lng, lat, code, status]
                column.append(tile)

            self.tiles.append(column) 


    def checkURL(self, url):

        try:
            urllib2.urlopen(url).read()        
        except:
            return False

        return True


    def download(self):

        if os.path.exists("./tiles") != True:
             os.mkdir("./tiles")

        print ''
        n = 1
        for column in self.tiles:
            for tile in column:

                tilePath = './tiles/tile_' + self.makeIdentifier(tile) + '.jpg'

                # If the tile with the expected identifier suffix already exists in the tiles directory,
                # assume that is the one we want (allows execution to continue later if interrupted).
                if os.path.exists(tilePath):
                    print 'Using existing tile ' + str(n) + '/' + str(self.nX*self.nY) + (
                    ', (i, j) = (' + str(tile[0]) + ',' + str(tile[1]) + ')' )

                else:
                    
                    mapurl = ''

                    if self.maptype == 'map':              mapurl = self.gen_MAP_URL(tile)
                    elif self.maptype == 'satellite':      mapurl = self.gen_SAT_URL(tile)       
                    elif self.maptype == 'terrain':        mapurl = self.gen_PHY_URL(tile)
                    elif self.maptype == 'sky':            mapurl = self.gen_SKY_URL(tile)

                    else:
                        print 'Unknown map type! Quitting. Humph'
                        sys.exit()
                        
                    if mapurl:

                        print 'Downloading tile ' + str(n) + '/' + str(self.nX*self.nY) + ', (i, j) = (' + str(tile[0]) + ',' + str(tile[1]) + ')'
                        grabPool.put( [ mapurl, self.makeIdentifier(tile) ] )
                        
                    else:
                            
                        print 'Tile ' + str(n) + '/' + str(self.nX*self.nY) + (
                            ', (i, j) = (' + str(tile[0]) + ',' + str(tile[1]) + ') is not stored by Google, and will be rendered black')
                        tile[3] = False

                n += 1
        grabPool.join()    

    
    def makeIdentifier(self, tile):

        identifier = self.maptype + '_' + str(self.zoom) + '_'
        if self.maptype == 'satellite':
            identifier += tile[2]
        else:
            identifier += str(tile[0]) + '_' + str(tile[1])
        return identifier

                
    def getTile(self, lng, lat):

        nTile = 1 << self.zoom

        # note, assume ranges are lng = (-180,180), lat = (-90,90)
        tilex = long(nTile * (float(lng) + 180.0)/360.0)
        tiley = long(nTile * (float(lat) + 90.0 )/180.0)

        if tilex == nTile: tilex -= 1
        if tilex<0: tilex = 0

        if tiley == nTile: tiley -= 1
        if tiley<0: tiley = 0  

        # the hybrid and terrain modes index the tiles descending with latitude 
        if self.maptype != 'satellite':
            tiley = nTile - 1 - tiley
            
        tile = (tilex, tiley)
        return tile        


    def gen_MAP_URL(self, tile):

        x = str(tile[0])
        y = str(tile[1])

        url = self.MAP_MODE_PREFIX + '&x=' + x + '&y=' + y + '&zoom=' + str(self.htmlzoom)
        return url

    
    def gen_SAT_URL(self, tile):

        code = tile[2]

        url = self.SAT_MODE_PREFIX + '&t=' + code
        return url


    def gen_PHY_URL(self, tile):

        x = str(tile[0])
        y = str(tile[1])

        url = self.PHY_MODE_PREFIX + '&x=' + x + '&y=' + y + '&zoom=' + str(self.htmlzoom)
        return url


    def gen_SKY_URL(self, tile):

        x = str(tile[0])
        y = str(tile[1])

        url = self.SKY_MODE_PREFIX + x + '_' + y + '_' + str(self.zoom) + '.jpg'
        return url

    
    def convertToBinary(self, x, n):

        b = ''
        for i in range(0,n):
            b = str((x >> i) & 1) + b
        return b   

           
    def genSatelliteTileCode(self, x, y):

        # In satellite mode, the tiles are indexed by a sequence of the letters q, r, s, t, where
        # there are 4^zoom tiles to index at each level. This works as indicated below:
        #
        #  zoom 0  zoom1      zoom 2              etc...
        #
        #  t       tq tr      tqq tqr   trq trr 
        #          tt ts      tqt tqs   trt trs
        #
        #                     ttq ttr   tsq tsr 
        #                     ttt tts   tst tss
        
        nTile = 1 << self.zoom
       
        if ((y < 0) or (nTile-1 < y)):
            return 'x'
        
        if ((x < 0) or (nTile-1 < x)):
            x = x % nTile
            if (x < 0):
                x += nTile;
                
        c = 't'

        # convert each to zoom-digit binary representation 
        bx = self.convertToBinary(x, self.zoom)
        by = self.convertToBinary(y, self.zoom)

        #                           q   r   s   t
        #    left(0)/right(1) (x)   0   1   1   0
        #    down(0)/up(1)    (y)   1   1   0   0

        for i in range(0, self.zoom):

            if (bx[i] == '0'):
                if(by[i] == '0'):
                    c += 't'
                else:
                    c += 'q'
            else:
                if(by[i] == '0'):
                    c += 's'
                else:
                    c += 'r'
               
        return c


    def getCoordsOfTile(self, tile):

        nTile = 1 << self.zoom

        width  = 360.0/float(nTile)
        height = 180.0/float(nTile)

        tiley = tile[1]
        if self.maptype != 'satellite':
            tiley = nTile - 1 - tiley

        X = -180.0 + float(tile[0]) * width
        Y = -90.0  + float(tiley) * height

        # coords of corners of tile
        LL = (X,       Y)
        UR = (X+width, Y+height)
        return [LL, UR]


    def crop(self, Map):

        # Crop off the excess space.
        # Get (lat, lon) in degrees of corners of image
        tileA = self.tiles[0][0]
        coordsA = self.getCoordsOfTile(tileA)
        
        tileB = self.tiles[self.nX-1][self.nY-1]
        coordsB = self.getCoordsOfTile(tileB)

        LL = (coordsA[0][0], coordsA[0][1])
        UR = (coordsB[1][0], coordsB[1][1])

        # (ax, ay) and (bx, by) are the image coords of the corners of the desired map:
        ax = (self.lonVal[0] - LL[0]) / (UR[0] - LL[0])
        ay = (self.yVal[0]   - LL[1]) / (UR[1] - LL[1])
        bx = (self.lonVal[1] - LL[0]) / (UR[0] - LL[0])
        by = (self.yVal[1]   - LL[1]) / (UR[1] - LL[1])

        ax = int(self.pX * ax)
        ay = int(self.pY * (1.0-ay))
        bx = int(self.pX * bx)
        by = int(self.pY * (1.0-by))

        #clamp to be safe
        if ax>=self.pX: ax=self.pX-1;
        if ax<0: ax=0;
        if bx>=self.pX: bx=self.pX-1;
        if bx<0: bx=0;
        if ay>=self.pY: ay=self.pY-1;
        if ay<0: ay=0;
        if by>=self.pY: by=self.pY-1;
        if by<0: by=0;
        
        box = [ax, by, bx, ay]
        return Map.crop(box)

      
    def stitch(self):

        print '\nStitching tiles'
        self.pX = 256 * self.nX
        self.pY = 256 * self.nY

        mode = "RGB"
        Map = Image.new(mode, (self.pX, self.pY))

        for i in range(0, self.nX):
            for j in range(0, self.nY):

                tile = self.tiles[i][j]
                if tile[3] == False:
                    continue
                
                path = './tiles/tile_' + self.makeIdentifier(tile) + '.jpg'

                # pixel coords of top left corner of this tile
                cX = 256 * i
                cY = self.pY - 256 * (j+1)

                im = Image.open(path)
                Map.paste(im, (cX, cY))

        cropMap = self.crop(Map)
                    
        # give the map file a semi-unique name, derived from the lower-left tile coords
        mappath = './stitched_' + self.makeIdentifier(self.tiles[0][0]) + '.jpg'
        cropMap.save(mappath)

        print 'Saved stitched map ' + mappath
        print 'Finished.'



############################ wxPython GUI interface ############################

# Frame dimensions
wX = 360
wY = 430

# border width
bW = 20

# coord panel height
hY = 180

class MainPanel(wx.Panel):

    def OnSetFocus(self, evt):
        print "OnSetFocus"
        evt.Skip()

    def OnKillFocus(self, evt):
        print "OnKillFocus"
        evt.Skip()

    def OnWindowDestroy(self, evt):
        print "OnWindowDestroy"
        evt.Skip()

    def __init__(self, parent, id):

        self.parent = parent
        
        pos = wx.Point(bW,bW)
        size = wx.Size(wX-2*bW, hY)
        hspace = 4
        wx.Panel.__init__(self, parent, -1, pos, size)
        

        # Lat/Lng direct entry section
        heading_LL = wx.StaticText(self, -1, "Lower left")
        heading_UR = wx.StaticText(self, -1, "Upper right")
        fW = 125

        lat_label = wx.StaticText(self, -1, "Latitude")
        lon_label = wx.StaticText(self, -1, "Longitude")
        
        self.latLL_text  = wx.TextCtrl(self, -1, "-90.0", size=(fW, -1))
        self.latLL_text.SetInsertionPoint(0)
        self.Bind( wx.EVT_TEXT, self.EvtTextChanged, self.latLL_text)

        self.lonLL_text  = wx.TextCtrl(self, -1, "-180.0", size=(fW, -1))
        self.lonLL_text.SetInsertionPoint(0)
        self.Bind( wx.EVT_TEXT, self.EvtTextChanged, self.lonLL_text)

        self.latUR_text  = wx.TextCtrl(self, -1, "90.0", size=(fW, -1))
        self.latUR_text.SetInsertionPoint(0)
        self.Bind( wx.EVT_TEXT, self.EvtTextChanged, self.latUR_text)

        self.lonUR_text  = wx.TextCtrl(self, -1, "180.0", size=(fW, -1))
        self.lonUR_text.SetInsertionPoint(0)
        self.Bind( wx.EVT_TEXT, self.EvtTextChanged, self.lonUR_text)

        coord_sizer = wx.FlexGridSizer(cols=3, hgap=4*hspace, vgap=2*hspace)
        coord_sizer.AddMany([ (0, 0),      heading_LL,      heading_UR,
                            lat_label,   self.latLL_text, self.latUR_text,
                            lon_label,   self.lonLL_text, self.lonUR_text,
                            (0, 0), (0,0), (0,0) ])

        # Lat/Lng code entry section
        code_label = wx.StaticText(self, -1, "Code: ")
        self.coordCode = wx.TextCtrl(self, -1, "", size=(fW*2, -1))
        self.coordCode.SetInsertionPoint(0)
        self.Bind( wx.EVT_TEXT, self.EvtTextChanged, self.coordCode)

        useCode_cb = wx.CheckBox(self, -1, "Use code?", wx.DefaultPosition)
        self.Bind( wx.EVT_CHECKBOX, self.EvtCoordCheckBox, useCode_cb)
        self.useCode = False

        code_sizer = wx.FlexGridSizer(cols=2, hgap=3*hspace, vgap=3*hspace)
        code_sizer.AddMany([ useCode_cb, (0,0),
                             code_label, self.coordCode,
                             (0, 0), (0,0) ])

        # 'Specify resolution' option enable checkbox
        self.useRes_rb = wx.RadioButton(self, -1, "Specify resolution", wx.DefaultPosition)
        self.useRes_rb.SetValue(True)
        self.Bind( wx.EVT_RADIOBUTTON, self.EvtResolutionRadioButton, self.useRes_rb)
        self.useResolution = True

        res_label = wx.StaticText(self, -1, "Approx. number of pixels: ")

        self.res_text  = wx.TextCtrl(self, -1, "512", size=(fW/2, -1))
        self.res_text.SetInsertionPoint(0)
        self.Bind( wx.EVT_TEXT, self.EvtTextChanged, self.res_text)

        res_sizer = wx.FlexGridSizer(cols=1, hgap=3*hspace, vgap=hspace)
        res_sizer.AddMany([ self.useRes_rb, (0,0) ])

        res_sizer = wx.FlexGridSizer(cols=2, hgap=3*hspace, vgap=3*hspace)
        res_sizer.AddMany([ self.useRes_rb, (0,0),
                            res_label, self.res_text,
                            (0, 0), (0,0) ])

        # 'Specify zoom level' option enable checkbox and entry
        self.useZoom_rb = wx.RadioButton(self, -1, "Specify zoom level", wx.DefaultPosition)
        self.useZoom_rb.SetValue(False)
        self.Bind( wx.EVT_RADIOBUTTON, self.EvtZoomRadioButton, self.useZoom_rb)
        self.useZoomLevel = False

        self.zoomInfo_label = wx.StaticText(self, -1, "(lowest = 0, highest = 19)")
        zoom_label = wx.StaticText(self, -1, "Zoom level: ")

        self.zoomLevel_text  = wx.TextCtrl(self, -1, "5", size=(fW/2, -1))
        self.zoomLevel_text.SetInsertionPoint(0)
        self.Bind( wx.EVT_TEXT, self.EvtTextChanged, self.zoomLevel_text)
        self.zoomLevel_text.Enable(False)

        zoom_sizer = wx.FlexGridSizer(cols=2, hgap=3*hspace, vgap=3*hspace)
        zoom_sizer.AddMany([ self.useZoom_rb, self.zoomInfo_label,
                             zoom_label, self.zoomLevel_text,
                             (0, 0), (0,0) ])

        # Map type selection radio box
        self.radioList = ['map', 'satellite', 'terrain', 'sky']
        rb = wx.RadioBox(self, -1, "Map type", wx.DefaultPosition, wx.DefaultSize,
                           self.radioList, 3, wx.RA_SPECIFY_COLS)
        self.Bind( wx.EVT_RADIOBOX, self.EvtRadioBox, rb)
        self.maptype = 'map'

        rbsizer = wx.BoxSizer(wx.HORIZONTAL)
        rbsizer.Add(rb, 0, wx.GROW|wx.ALL, hspace)

        # Tiles info
        self.tilesInfo_label  = wx.StaticText(self, -1, '', size=(fW, -1))
        ziFont = wx.Font(10, wx.NORMAL, wx.NORMAL, wx.BOLD, False, u'Courier')
        self.tilesInfo_label.SetFont(ziFont)

        # Run button
        b = wx.Button(self, -1, "Run")
        self.Bind(wx.EVT_BUTTON, self.OnRun, b)

        bsizer = wx.BoxSizer(wx.HORIZONTAL)
        bsizer.Add(b, 0, wx.GROW|wx.ALL, hspace)

        # UI layout
        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(coord_sizer, 0, wx.GROW)
        border.Add(code_sizer, 0, wx.GROW)
        border.Add(res_sizer, 0, wx.GROW)
        border.Add(zoom_sizer, 0, wx.GROW)
        border.Add(rbsizer, 0, wx.GROW)
        border.AddSpacer(15)
        border.Add(self.tilesInfo_label, 0, wx.GROW)
        border.AddSpacer(5)
        border.Add(bsizer, 0, wx.GROW)
        
        self.SetSizer(border)
        self.SetAutoLayout(True)
        border.Fit(self)

        self.updateMapParams()
        

    def updateMapParams(self):

        lat = None
        lon = None

        if self.useCode == True:

            coords = self.coordCode.GetValue().split('_')

            if len(coords) != 4:
                print 'Code cannot be parsed into coordinates, unable to generate map.'
                return False

            # Ensure that the 0th corner is lower left, even if the user didn't make it so
            try:
                lat = (coords[1], coords[3])
                if float(lat[1]) < float(lat[0]):
                    lat = (coords[3], coords[1])
                lon = (coords[0], coords[2])
                if float(lon[1]) < float(lon[0]):
                    lon = (coords[2], coords[0])
            except:
                print 'Code cannot be parsed into coordinates, unable to generate map.'
                return False
                
        else:
            
            # Ensure that the 0th corner is lower left, even if the user didn't make it so
            lat = (self.latLL_text.GetValue(), self.latUR_text.GetValue())

            try:
                if float(lat[1]) < float(lat[0]):
                    lat = (self.latUR_text.GetValue(), self.latLL_text.GetValue())
                lon = (self.lonLL_text.GetValue(), self.lonUR_text.GetValue())
                if float(lon[1]) < float(lon[0]):
                    lon = ( self.lonUR_text.GetValue(), self.lonLL_text.GetValue())
            except:
                print 'Invalid longitude/latitude values, unable to generate map.'
                return False

        zoomLevel = -1
        if self.useZoom_rb.GetValue():
            try:
                zoomLevel = int(self.zoomLevel_text.GetValue())
            except:
                pass

        res = 0
        if self.useRes_rb.GetValue():
            try:
               res = int(self.res_text.GetValue())
            except:
                pass

        self.gmap = StitchedMap(lat, lon, res, zoomLevel, self.maptype)

        tileRange = self.gmap.computeTileRange()
        tileA = tileRange[0]
        tileB = tileRange[1]
        nX = abs(tileB[0] - tileA[0]) + 1
        nY = abs(tileB[1] - tileA[1]) + 1

        tileinfo = ' Will download ' + str(nX*nY) + ' tiles: (' + str(tileA[0]) + ',' + str(tileA[1]) + ') to (' + str(tileB[0]) + ',' + str(tileB[1]) + ')'
        self.tilesInfo_label.SetLabel(tileinfo)

        return True
         

    def OnRun(self, evt):

        if self.updateMapParams():
            self.gmap.generate()


    def EvtRadioBox(self, event):

        maptype = ''
        i = event.GetInt()
        if i == 0:   self.maptype = 'map'
        elif i == 1: self.maptype = 'satellite'
        elif i == 2: self.maptype = 'terrain'
        else: self.maptype = 'sky'

        self.updateMapParams()


    def EvtCoordCheckBox(self, event):
        
        self.useCode = event.Checked()
        if self.useCode:
            self.coordCode.Enable(True)
        else:
            self.coordCode.Enable(False)
        self.updateMapParams()
         

    def EvtResolutionRadioButton(self, event):

        self.zoomLevel_text.Enable(False)
        self.res_text.Enable(True)
        self.updateMapParams()

              
    def EvtZoomRadioButton(self, event):

        self.zoomLevel_text.Enable(True)
        self.res_text.Enable(False)
        self.updateMapParams()

    def EvtTextChanged(self, event):

        if self.useZoom_rb.GetValue():

            zoomLevel = 0
            try:
                zoomLevel = int(self.zoomLevel_text.GetValue())
            except:
                pass

            minZoom = 0
            maxZoom = 19 
            if (zoomLevel<minZoom):
                zoomLevel = minZoom
                self.zoomLevel_text.SetValue(str(zoomLevel))
            if (zoomLevel>maxZoom):
                zoomLevel = maxZoom
                self.zoomLevel_text.SetValue(str(zoomLevel))
            
        self.updateMapParams()


class MainWindow(wx.Frame):
    
    def __init__(self, parent, id, title):

        N = 10
        print "*************** Stitch v3.0 ***************"
        print "Starting " + str(N) + " download threads"
        self.threads = []
        
        for x in range(N):
            thread = ThreadingClass()
            thread.start()
            self.threads.append(thread)
            
        wx.Frame.__init__(self, parent, wx.ID_ANY, title, wx.DefaultPosition, wx.Size(wX, wY))
        controlPanel = MainPanel(self, -1)

    def __del__(self):

        for thread in self.threads:
            thread.join()

        print "Terminated download threads. Quitting."

 
# Entry point
app = wx.PySimpleApp()

frame = MainWindow(None, -1, "Stitch")

frame.Show(True)

app.MainLoop()

