import rasterio
import rasterio.plot
import rasterio.mask
from shapely import geometry
import numpy as np
import math
from skimage.feature import match_template
import matplotlib.pyplot as plt

def get_image_arrays():    

    # read in the 'from' and 'to' images as numpy arrays (currently assumes multiple layers in the from and to image files)
    fromRaster = rasterio.open('from.tif')
    fromHeight =  fromRaster.read(3, masked=True) # read band to numpy array
    fromStd = fromRaster.read(6, masked=True)
    toRaster = rasterio.open('to.tif')
    toHeight = toRaster.read(3, masked=True)
    toStd = toRaster.read(6, masked=True) 
    
    # create a polygon defining the extents of the geospatial overlap
    fromLRBT = list(rasterio.plot.plotting_extent(fromRaster)) # LRBT = [left, right, bottom, top]
    toLRBT = list(rasterio.plot.plotting_extent(toRaster))
    extentsLRBT = list()
    extentsLRBT.append(max(fromLRBT[0], toLRBT[0]))
    extentsLRBT.append(min(fromLRBT[1], toLRBT[1]))
    extentsLRBT.append(max(fromLRBT[2], toLRBT[2]))
    extentsLRBT.append(min(fromLRBT[3], toLRBT[3]))
    bbox = list()
    bbox.append([extentsLRBT[0], extentsLRBT[2]]) # Left Bottom
    bbox.append([extentsLRBT[1], extentsLRBT[2]]) # Right Bottom
    bbox.append([extentsLRBT[1], extentsLRBT[3]]) # Right Top
    bbox.append([extentsLRBT[0], extentsLRBT[3]]) # Left Top
    bpoly = geometry.Polygon(bbox)
    
    # crop from and to images to bounding box
    fromHeightCropped, t = rasterio.mask.mask(fromRaster, [bpoly], crop=True, indexes=3)
    fromErrorCropped, t = rasterio.mask.mask(fromRaster, [bpoly], crop=True, indexes=6)
    toHeightCropped, t = rasterio.mask.mask(toRaster, [bpoly], crop=True, indexes=3)
    toErrorCropped, t = rasterio.mask.mask(toRaster, [bpoly], crop=True, indexes=6)

    return fromHeightCropped, fromErrorCropped, toHeightCropped, toErrorCropped
    

def piv(templateSize, stepSize):

    # get image arrays of common (overlapping) area
    fromHeight, fromError, toHeight, toError = get_image_arrays()

    # determine number of search areas in horizontal (u) and vertical (v)
    searchSize = templateSize*2
    imageShape = fromHeight.shape # [height, width]
    uCount = math.floor((imageShape[1]-searchSize) / stepSize)
    print("uCount=%u" % uCount)
    vCount = math.floor((imageShape[0]-searchSize) / stepSize)
    print("vCount=%u" % vCount)

    # cycle through each search area
    for i in range(vCount):
        print("i=%u" % i)
        for j in range(uCount):
            print("j=%u" % j)
            # get template area data from the 'from' height and error images
            templateStartU = int(j*stepSize + math.ceil(templateSize/2))
            print("templateStartU=%u" % templateStartU)
            templateEndU = int(j*stepSize + math.ceil(templateSize/2) + templateSize)
            print("templateEndU=%u" % templateEndU)
            templateStartV = int(i*stepSize + math.ceil(templateSize/2))
            print("templateStartV=%u" % templateStartV)
            templateEndV = int(i*stepSize + math.ceil(templateSize/2) + templateSize)
            print("templateEndV=%u" % templateEndV)
            templateHeight = fromHeight[templateStartU:templateEndU, templateStartV:templateEndV].copy()
            print(templateHeight.shape)
            templateError = fromError[templateStartU:templateEndU, templateStartV:templateEndV].copy()
            # get search area data from the 'to' height and error images
            searchStartU = int(j*stepSize)
            print("searchStartU=%u" % searchStartU)
            searchEndU = int(j*stepSize + 2*templateSize)
            print("searchEndU=%u" % searchEndU)
            searchStartV = int(i*stepSize)
            print("searchStartV=%u" % searchStartV)
            searchEndV = int(i*stepSize + 2*templateSize)
            print("searchEndV=%u" % searchEndV)
            searchHeight = toHeight[searchStartU:searchEndU, searchStartV:searchEndV].copy()
            print(searchHeight.shape)
            searchError = toError[searchStartU:searchEndU, searchStartV:searchEndV].copy()

            # NEED TO HANDLE EMPTY CELLS (value = -9999 or NaN)

            # move to next area if the template is flat, which breaks the correlation computation
            if (templateHeight.max() - templateHeight.min()) == 0:
                print("flat template")
                # plt.imshow(fromHeight)
                # plt.title("From")
                # plt.show()
                # plt.imshow(toHeight)
                # plt.title("To")
                # plt.show()
                continue
            
            # normalized cross correlation between the template and search area height data
            
            test = match_template(searchHeight, templateHeight)
            mask = templateHeight == -9999
            templateHeight[mask] = 0
            mask = searchHeight == -9999
            searchHeight[mask] = 0
            templateHeight /= templateHeight.max()
            searchHeight /= searchHeight.max()

            # plt.imshow(fromHeight, cmap=plt.cm.gray)
            # plt.title("From")
            # plt.show()
            # plt.imshow(toHeight, cmap=plt.cm.gray)
            # plt.title("To")
            # plt.show()

            fig1 = plt.figure()
            ax1 = plt.subplot(1, 3, 1)
            ax2 = plt.subplot(1, 3, 2)
            ax3 = plt.subplot(1, 3, 3)
            ax1.set_title('Template')
            ax2.set_title('Search')
            ax3.set_title('NCC')
            ax1.imshow(templateHeight, cmap=plt.cm.gray)
            ax2.imshow(searchHeight, cmap=plt.cm.gray)
            ax3.imshow(test, cmap=plt.cm.gray)

            fig2 = plt.figure()
            ax1 = plt.subplot(1, 2, 1)
            ax2 = plt.subplot(1, 2, 2)
            ax1.set_title('FROM')
            ax2.set_title('TO')
            ax1.imshow(fromHeight, cmap=plt.cm.gray)
            ax2.imshow(toHeight, cmap=plt.cm.gray)
            plt.show()







