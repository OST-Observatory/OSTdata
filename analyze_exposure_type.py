import sys
import os

from pathlib import Path

# from scipy.ndimage import median_filter, maximum_filter
# from scipy.interpolate import InterpolatedUnivariateSpline
# from scipy.ndimage import median_filter

from utilities import analyze_and_update_exposure_type

if __name__ == "__main__":

    plot_histogram = False

    dir_path = sys.argv[1]

    outfile = open("results.dat", "w")

    skip_file = open("files_to_skip.dat", "r")

    files_to_skip = skip_file.read()

    skip_file.close()

    skip_file = open("files_to_skip.dat", "w")

    skip_file.writelines(files_to_skip)

    for (root, dirs, files) in os.walk(dir_path, topdown=True):
        for f in files:

            file_path = Path(root, f)
            # # print(dir(file_path))
            # print(file_path.name)

            if str(file_path) in files_to_skip:
                continue

            status, image_type, estimated_image_type, spectrum_type, instrument = analyze_and_update_exposure_type(
                file_path,
                plot_histogram=False,
                print_to_terminal=True,
            )
            if not status:
                continue

            if ((estimated_image_type != image_type or image_type == 'light') and
                    not (estimated_image_type == 'light' and image_type == 'wave')):
                outfile.write(
                    f'Image type: {image_type} \tEstimated: {estimated_image_type}\tSpectra type: {spectrum_type}'
                    f'\tInstrument: {instrument}\n'
                )
                outfile.write(
                    f'File: {file_path.absolute()}\n\n'
                )

            skip_file.write(f'{file_path}\n')

        print('---------------------------------------------')
        print()
        outfile.write(f'-------------------------------------------------\n')

    #   Model parameter:
    #       instrument: baches or dados --> spectra_type
    #       derived_exposure_type = bias, dark, wave, flat, light, over_exposed
    #       add flag if derived_exposure_type and Header value are consistent

    outfile.close()
    skip_file.close()
