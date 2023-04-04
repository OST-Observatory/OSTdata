from .analyze_fits_header import analyze_fits

from .analyze_image_and_video_header import analyze_image, analyze_ser

############################################################################

def set_file_info(datafile):
    '''
        Extract informations from the data file and add those to the DataFile
        model

        Parameters
        ----------
        datafile        : `obs_run.models.DataFile` object
            DataFile instance

        # pk             : integer`
        #     ID of the DataFile model
    '''
    #   File type
    file_type = datafile.file_type

    if file_type == 'FITS':
        #   Analyze FITS
        analyze_fits(datafile)

    elif file_type in ['JPG', 'CR2']:
        #   Analyze image files
        analyze_image(datafile)

    elif file_type == 'SER':
        #   Analyze SER video files
        analyze_ser(datafile)

