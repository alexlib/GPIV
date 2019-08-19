import rasterio
import numpy as np
import sys
from skimage.feature import match_template
import matplotlib.pyplot as plt
import matplotlib.patches
import math
import json


def get_image_arrays(
    before_height_file,
    before_uncertainty_file,
    after_height_file,
    after_uncertainty_file,
    propagate):    

    before_height_source = rasterio.open(before_height_file)
    before_height = before_height_source.read(1)
    after_height_source = rasterio.open(after_height_file)
    after_height = after_height_source.read(1)

    if propagate:
        before_uncertainty = rasterio.open(before_uncertainty_file).read(1)
        after_uncertainty = rasterio.open(after_uncertainty_file).read(1)
    else:
        before_uncertainty = []
        after_uncertainty = []

    # get raster coordinate transformation for later use
    before_geo_transform = np.reshape(np.asarray(before_height_source.transform), (3,3))
    after_geo_transform = np.reshape(np.asarray(after_height_source.transform), (3,3))
    if not np.array_equal(before_geo_transform, after_geo_transform):
        print("The extent and/or datum of the 'before' and 'after' DEMs is not equivalent.")
        sys.exit()    

    return before_height, before_uncertainty, after_height, after_uncertainty, before_geo_transform


def run_piv(
    before_height, 
    before_uncertainty, 
    after_height, 
    after_uncertainty, 
    geo_transform, 
    template_size, 
    step_size, 
    propagate,
    output_base_name):
    
    piv_origins = []
    piv_vectors = []
    if propagate:
        peak_covariance = []
        numeric_partial_derivative_increment = 0.000001

    status_figure = plt.figure()
    before_axis = plt.subplot(1, 2, 1)
    after_axis = plt.subplot(1, 2, 2)

    search_size = template_size * 2 # size of area to be searched for match in 'after' image
    number_horizontal_computations = math.floor((before_height.shape[1]-search_size) / step_size)
    number_vertical_computations = math.floor((before_height.shape[0]-search_size) / step_size)

    for vt_count in range(number_vertical_computations):
        for hz_count in range(number_horizontal_computations):

            hz_template_start = int(hz_count*step_size + math.ceil(template_size/2))
            hz_template_end = int(hz_count*step_size + math.ceil(template_size/2) + template_size)
            vt_template_start = int(vt_count*step_size + math.ceil(template_size/2))
            vt_template_end = int(vt_count*step_size + math.ceil(template_size/2) + template_size)
            height_template = before_height[vt_template_start:vt_template_end, hz_template_start:hz_template_end].copy()
            
            hz_search_start = int(hz_count*step_size)
            hz_search_end = int(hz_count*step_size + search_size + (template_size % 2)) # the modulo addition forces the search area to be symmetric around odd-sized templates
            vt_search_start = int(vt_count*step_size)
            vt_search_end = int(vt_count*step_size + search_size + (template_size % 2)) 
            height_search = after_height[vt_search_start:vt_search_end, hz_search_start:hz_search_end].copy()            

            show_piv_location(
                before_height, after_height,
                before_axis, after_axis,
                hz_template_start, vt_template_start,
                hz_search_start, vt_search_start,
                template_size, search_size)     

            # flat template produces a divide by zero in normalized cross correlation
            if ((height_template.max() - height_template.min()) == 0): 
                continue

            normalized_cross_correlation = match_template(height_search, height_template) # uses FFT based correlation
            correlation_max = np.where(normalized_cross_correlation == np.amax(normalized_cross_correlation))

            # peak location on edges of correlation matrix breaks sub-pixel peak interpolation
            if (correlation_max[0][0]==0 or
                    correlation_max[1][0]==0 or 
                    correlation_max[0][0]==normalized_cross_correlation.shape[0]-1 or 
                    correlation_max[1][0]==normalized_cross_correlation.shape[1]-1): 
                continue

            subpixel_peak = get_subpixel_peak(
                normalized_cross_correlation[
                    correlation_max[0][0]-1:correlation_max[0][0]+2,
                    correlation_max[1][0]-1:correlation_max[1][0]+2])
            
            piv_origins.append(((hz_count*step_size + template_size - (1 - template_size % 2)*0.5), # modulo operator adjusts even-sized template origins to be between pixel centers
                                (vt_count*step_size + template_size - (1 - template_size % 2)*0.5)))
            piv_vectors.append(((correlation_max[1][0] - math.ceil(template_size/2) + subpixel_peak[0]),
                                (correlation_max[0][0] - math.ceil(template_size/2) + subpixel_peak[1])))

            if propagate:
                uncertainty_template = before_uncertainty[vt_template_start:vt_template_end, hz_template_start:hz_template_end].copy()
                uncertainty_search = after_uncertainty[vt_search_start:vt_search_end, hz_search_start:hz_search_end].copy()    

                # propagate raster error into the 3x3 patch of correlation values that are centered on the correlation peak
                correlation_covariance = propagate_pixel_into_correlation(
                    height_template,
                    uncertainty_template, 
                    height_search[correlation_max[0][0]-1:correlation_max[0][0]+template_size+1, correlation_max[1][0]-1:correlation_max[1][0]+template_size+1], # templateSize+2 x templateSize+2 subarray of the search array,
                    uncertainty_search[correlation_max[0][0]-1:correlation_max[0][0]+template_size+1, correlation_max[1][0]-1:correlation_max[1][0]+template_size+1], # templateSize+2 x templateSize+2 subarray of the search error array
                    normalized_cross_correlation[correlation_max[0][0]-1:correlation_max[0][0]+2, correlation_max[1][0]-1:correlation_max[1][0]+2], # 3x3 array of correlation values centered on the correlation peak
                    numeric_partial_derivative_increment) 

                # propagate the correlation covariance into the subpixel peak location
                subpixel_peak_covariance = propagate_correlation_into_subpixel_peak(
                    normalized_cross_correlation[correlation_max[0][0]-1:correlation_max[0][0]+2, correlation_max[1][0]-1:correlation_max[1][0]+2],
                    correlation_covariance,
                    subpixel_peak,
                    numeric_partial_derivative_increment)
                
                peak_covariance.append(subpixel_peak_covariance.tolist())   

    plt.close(status_figure)

    export_piv(
        piv_origins,
        piv_vectors,
        geo_transform,
        output_base_name)

    if propagate:
        export_uncertainty(
            peak_covariance,
            geo_transform,
            output_base_name)


def show_piv_location(
    before_height, after_height,
    before_axis, after_axis,
    hz_template_start, vt_template_start,
    hz_search_start, vt_search_start,
    template_size, search_size):

    plt.sca(before_axis)
    plt.cla()
    before_axis.set_title('Before')
    before_axis.imshow(before_height, cmap=plt.cm.gray)
    before_axis.add_patch(matplotlib.patches.Rectangle(
        (hz_template_start, vt_template_start), 
        template_size-1, 
        template_size-1, 
        linewidth=1, 
        edgecolor='r',
        fill=None))
    
    plt.sca(after_axis)
    plt.cla()
    after_axis.set_title('After')            
    after_axis.imshow(after_height, cmap=plt.cm.gray)            
    after_axis.add_patch(matplotlib.patches.Rectangle(
        (hz_search_start,vt_search_start), 
        search_size-1, 
        search_size-1, 
        linewidth=1, 
        edgecolor='r',
        fill=None))

    plt.pause(0.1)


def get_subpixel_peak(normalized_cross_correlation):

    dx = (normalized_cross_correlation[1,2] - normalized_cross_correlation[1,0]) / 2
    dxx = normalized_cross_correlation[1,2] + normalized_cross_correlation[1,0] - 2*normalized_cross_correlation[1,1]
    dy = (normalized_cross_correlation[2,1] - normalized_cross_correlation[0,1]) / 2
    dyy = normalized_cross_correlation[2,1] + normalized_cross_correlation[0,1] - 2*normalized_cross_correlation[1,1]
    dxy = (normalized_cross_correlation[2,2] - normalized_cross_correlation[2,0] - normalized_cross_correlation[0,2] + normalized_cross_correlation[0,0]) / 4
    
    # hz_delta is postive left-to-right; vt_delta is postive top-to-bottom
    hz_delta = -(dyy*dx - dxy*dy) / (dxx*dyy - dxy*dxy)
    vt_delta = -(dxx*dy - dxy*dx) / (dxx*dyy - dxy*dxy)

    return [hz_delta, vt_delta]


def propagate_pixel_into_correlation(
    height_template,
    uncertainty_template, 
    height_search,
    uncertainty_search,
    normalized_cross_correlation,
    numeric_partial_diff_increment):

    template_covariance_vector = np.square(uncertainty_template.reshape(uncertainty_template.size,)) # convert array to vector, row-by-row, and square the standard deviations into variances
    search_covariance_vector = np.square(uncertainty_search.reshape(uncertainty_search.size,))
    covariance_matrix = np.diag(np.hstack((template_covariance_vector, search_covariance_vector)))

    jacobian = get_correlation_jacobian(height_template, height_search, normalized_cross_correlation, numeric_partial_diff_increment)    
    # Propagate the template and search area errors into the 9 correlation elements
    # The covariance order is by row of the ncc array (i.e., ncc[0,0], ncc[0,1], ncc[0,2], ncc[1,0], ncc[1,1], ...)
    correlation_covariance = np.matmul(jacobian,np.matmul(covariance_matrix,jacobian.T))

    return correlation_covariance


def get_correlation_jacobian(template,
    search,
    normalized_cross_correlation,
    numeric_partial_derivative_increment):

    number_template_rows, number_template_columns = template.shape
    number_search_rows, number_search_columns = search.shape
    jacobian = np.zeros((9, template.size + search.size))
    normalized_template = (template - np.mean(template)) / (np.std(template))

    # cycle through the 3x3 correlation array
    for row_correlation in range(3):
        for col_correlation in range(3):
            search_subarea = search[row_correlation:row_correlation+number_template_rows, col_correlation:col_correlation+number_template_columns]
            normalized_search_subarea = (search_subarea - np.mean(search_subarea)) / (np.std(search_subarea))

            template_partial_derivatives = np.zeros((number_template_rows, number_template_columns))
            search_partial_derivatives = np.zeros((number_search_rows, number_search_columns))

            # cycle through each pixel in the template and the search subarea and numerically estimate
            # its partial derivate with respect to the normalized cross correlation
            for row_template in range(number_template_rows):
                for col_template in range(number_template_columns):
                    perturbed_template = template.copy()
                    perturbed_template[row_template,col_template] += numeric_partial_derivative_increment
                    perturbed_search_subarea = search_subarea.copy()
                    perturbed_search_subarea[row_template,col_template] += numeric_partial_derivative_increment

                    # spatial domain normalized cross correlation (i.e., does not use the FFT)
                    # about 20x faster than using skimage's FFT based match_template method
                    normalized_perturbed_template = (perturbed_template - np.mean(perturbed_template)) / (np.std(perturbed_template))
                    normalized_perturbed_search_subarea = (perturbed_search_subarea - np.mean(perturbed_search_subarea)) / (np.std(perturbed_search_subarea))
                    perturbed_template_normalized_cross_correlation = np.sum(normalized_perturbed_template * normalized_search_subarea) / template.size
                    perturbed_search_subarea_normalized_cross_correlation = np.sum(normalized_template * normalized_perturbed_search_subarea) / template.size
                    
                    # storage location adjustment by row_correlation and col_correlation accounts for the larger size of the search area than the template area
                    template_partial_derivatives[row_template, col_template] = (perturbed_template_normalized_cross_correlation - ncc[row_correlation,col_correlation]) / numeric_partial_derivative_increment
                    search_partial_derivatives[row_correlation+row_template, col_correlation+col_template] = (perturbed_search_subarea_normalized_cross_correlation - ncc[row_correlation, col_correlation]) / numeric_partial_derivative_increment 

            # reshape the partial derivatives from their current array form to vector form and store in the Jacobian
            # we match the row-by-row pattern used to form the covariance matrix in the calling function
            jacobian[row_correlation*3+col_correlation, 0:template.size] = template_partial_derivatives.reshape(template_partial_derivatives.size,)
            jacobian[row_correlation*3+col_correlation, template.size:template.size+search.size] = search_partial_derivatives.reshape(search_partial_derivatives.size,)

    return jacobian


def propagate_correlation_into_subpixel_peak(
    correlation,
    correlation_covariance,
    subpixel_peak,
    numeric_partial_derivative_increment):

    jacobian = np.zeros((2,9))

    # cycle through the 3x3 correlation array, row-by-row, and create the jacobian matrix
    for row_correlation in range(3):
        for col_correlation in range(3):
            perturbed_correlation = ncc.copy()
            perturbed_correlation[row_correlation,col_correlation] += numeric_partial_derivative_increment            
            perturbed_hz_delta, perturbed_vt_delta = get_subpixel_peak(perturbed_correlation)            
            jacobian[0,row_correlation*3+col_correlation] = (perturbed_hz_delta - deltaUV[0]) / numeric_partial_derivative_increment
            jacobian[1,row_correlation*3+col_correlation] = (perturbed_vt_delta - deltaUV[1]) / numeric_partial_derivative_increment
    
    # propagate the 3x3 array of correlation uncertainties into the sub-pixel U and V direction offsets
    subpixel_peak_covariance = np.matmul(jacobian, np.matmul(correlation_covariance, jacobian.T))
        
    return subpixel_peak_covariance


def export_piv(
    piv_origins,
    piv_vectors,
    geo_transform,
    output_base_name):

    # convert from pixels to ground distance
    piv_origins = np.asarray(piv_origins)        
    piv_origins *= geo_transform[0,0] # scale by pixel ground size
    piv_origins[:,0] += geo_transform[0,2] # offset by leftmost pixel to get ground coordinate
    piv_origins[:,1] = geo_transform[1,2] - piv_origins[:,1] # subtract from uppermost pixel to get ground coordinate
    
    piv_vectors = np.asarray(piv_vectors)
    piv_vectors *= geo_transform[0,0] # scale by pixel ground size
    
    origins_vectors = np.concatenate((piv_origins, piv_vectors), axis=1)
    json.dump(origins_vectors.tolist(), open(output_base_name + "_origins_vectors.json", "w"))
    print("PIV origins and displacement vectors saved to file '{}_origins_vectors.json'".format(output_base_name))


def export_uncertainty(
    peak_covariance,
    geo_transform,
    output_base_name):

    peak_covariance = np.asarray(peak_covariance)
    peak_covariance *= geo_transform[0,0]**2

    json.dump(peak_covariance.tolist(), open(output_base_name + "_covariance_matrices.json", "w"))
    print("PIV displacement vector covariance matrices saved to file '{}_covariance_matrices.json'".format(output_base_name))