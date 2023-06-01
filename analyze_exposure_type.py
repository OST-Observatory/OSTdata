import sys
import os

from pathlib import Path

from astropy.io import fits
from astropy.visualization import simple_norm

from scipy.ndimage import median_filter, maximum_filter
from scipy.interpolate import InterpolatedUnivariateSpline

import matplotlib.pyplot as plt

import numpy as np
# from scipy.ndimage import median_filter
from scipy import ndimage, signal

if __name__ == "__main__":

    figure = False

    dir_path = sys.argv[1]

    outfile = open("results.dat", "w")

    for (root,dirs,files) in os.walk(dir_path, topdown=True):
        for f in files:
            file_path = Path(root, f)

            suffix = file_path.suffix
            if suffix in ['.fit', '.fits', '.FIT', '.FITS']:
                print('File: ', file_path.absolute())

                header = fits.getheader(file_path, 0)

                imagetyp = header.get('IMAGETYP', 'UK')
                if imagetyp == 'Flat Field':
                    imagetyp = 'flat'
                if imagetyp == 'Dark Frame':
                    imagetyp = 'dark'
                if imagetyp == 'Light Frame':
                    imagetyp = 'light'
                if imagetyp == 'Bias Frame':
                    imagetyp = 'bias'
                objectname = header.get('OBJECT', 'UK')
                exptime = header.get('EXPTIME', -1)

                image_data_original = fits.getdata(file_path, 0)

                img_shape = image_data_original.shape
                # print(image_data_original.shape)
                # print(image_data_original.ndim)

                if image_data_original.ndim > 2:
                    continue

                image_data = ndimage.median_filter(image_data_original, size=10)

                if figure:
                    fig = plt.figure(figsize=(20, 7))
                    ax1 = plt.subplot(1, 2, 1)
                    ax2 = plt.subplot(1, 2, 2)
                    # ax = fig.add_subplot(1, 1, 1)

                    ax1.hist(image_data.flatten(), bins='auto')
                    # plt.show()

                    # plt.imshow(image_data, cmap='gray', vmin=2.6E3, vmax=3E3)
                    norm = simple_norm(image_data, 'log')
                    ax2.imshow(image_data, cmap='gray', origin='lower', norm=norm)
                    # ax2.colorbar()
                    plt.show()
                    plt.close()

                histogram = ndimage.histogram(image_data, 0, 65000, 600)
                max_histo_id = np.argmax(histogram)
                n_non_zero_histo = len(np.nonzero(histogram)[0])

                median = np.median(image_data)
                mean = np.mean(image_data)
                variance = np.var(image_data)
                standard = np.std(image_data)

                y_sum = np.sum(image_data_original, axis=1)
                y_mean = np.mean(image_data_original, axis=1)
                # print(dir(image_data_original))
                # print(image_data_original.shape)
                # print(len(y_sum))
                # print(y_sum)

                id_y_mean_mid = int(len(y_mean) * 0.5)
                y_mid_mean_value = y_mean[id_y_mean_mid]
                print(y_mid_mean_value)

                y_sum_min = np.min(y_sum)
                # y_sum_mean = np.mean(y_sum)
                y_sum_mean = np.mean(y_sum-y_sum_min)
                y_sum_median = np.median(y_sum-y_sum_min)
                y_sum_standard = np.std(y_sum)
                # print(y_sum_mean)
                # print(y_sum_median)
                # print(y_sum_standard)
                # print(y_sum_min)
                # print(
                #     # signal.find_peaks(y_sum, height=y_sum_mean, width=15)
                #     # signal.find_peaks(y_sum-y_sum_min, height=y_sum_mean, width=15)
                #     # signal.find_peaks(y_sum-y_sum_min, height=y_sum_median, width=15)
                #     # signal.find_peaks(y_sum, height=y_sum_min, width=15, rel_height=0.9)
                    # signal.find_peaks(y_sum-y_sum_min, height=y_sum_median, width=130, rel_height=0.9)
                    # )

                spectra_type = None

                dados_spectra = signal.find_peaks(
                    y_sum-y_sum_min,
                    height=y_sum_median,
                    # height=y_sum_mean,
                    width=(132, 139),
                    rel_height=0.9,
                    prominence=30000.,
                    )
                print(dados_spectra)
                if dados_spectra[0].size > 1:
                    spectra_type = 'dados'
                    # print(dados_spectra)
                else:
                    baches_spectra = signal.find_peaks(
                    y_sum-y_sum_min,
                    height=y_sum_median,
                    # width=(16, 30),
                    width=(16, 50),
                    # rel_height=0.9,
                    )

                    n_order = baches_spectra[0].size

                    if n_order >= 4:
                        spectra_type = 'baches'
                        print(baches_spectra)
                        # print(baches_spectra[-1])
                        # print(baches_spectra[-1]['right_ips'])

                        x_sum_order = 0.
                        n_pixel_in_orders = 0
                        for i in range(0,n_order):
                            start_order = int(baches_spectra[-1]['left_ips'][i])
                            end_order = int(baches_spectra[-1]['right_ips'][i])

                            x_sum_order += np.sum(
                                image_data_original[start_order:end_order,:]
                                )
                            n_pixel_in_orders += (end_order - start_order) \
                                                 * img_shape[1]

                        flux_in_orders_average = x_sum_order / n_pixel_in_orders
                        print(flux_in_orders_average, n_pixel_in_orders)

                        # variance, standard = 0., 0.
                        # for i in range(0,n_order):
                        #     start_order = int(baches_spectra[-1]['left_ips'][i])
                        #     end_order = int(baches_spectra[-1]['right_ips'][i])
                        #
                        #     x_sum_order = np.sum(
                        #         image_data_original[start_order:end_order,:],
                        #         axis=0,
                        #         )
                        #     # x_sum_order_index_max = np.argmax(x_sum_order)
                        #
                        #     x_sum_order_median_filtered = median_filter(
                        #         x_sum_order,
                        #         size=40,
                        #         )
                        #     x_sum_order_median_max_filtered = maximum_filter(
                        #         x_sum_order_median_filtered,
                        #         size=40,
                        #         )
                        #
                        #     norm_fit = InterpolatedUnivariateSpline(
                        #         np.arange(len(x_sum_order_median_max_filtered)),
                        #         x_sum_order_median_max_filtered,
                        #         k=2,
                        #         )
                        #
                        #     #   Normalize spectrum
                        #     x_data = np.arange(len(x_sum_order))
                        #     cont = norm_fit(x_data)
                        #     x_sum_order_norm = x_sum_order / cont
                        #
                        #     mask = np.argwhere(x_sum_order_norm > 1.)
                        #     x_sum_order_norm[mask] = 1.
                        #
                        #     variance += np.var(x_sum_order_norm)
                        #     standard += np.std(x_sum_order_norm)
                        #
                        # print(
                        #     variance/n_order,
                        #     standard/n_order,
                        #     )

                        # start_order = int(baches_spectra[-1]['left_ips'][2])
                        # end_order = int(baches_spectra[-1]['right_ips'][2])
                        #
                        # x_sum_order = np.sum(
                        #     image_data_original[start_order:end_order,:],
                        #     axis=0,
                        #     )
                        # # x_sum_order_index_max = np.argmax(x_sum_order)
                        #
                        # x_sum_order_median_filtered = median_filter(
                        #     x_sum_order,
                        #     size=40,
                        #     )
                        # x_sum_order_median_max_filtered = maximum_filter(
                        #     x_sum_order_median_filtered,
                        #     size=40,
                        #     )
                        #
                        # norm_fit = InterpolatedUnivariateSpline(
                        #     np.arange(len(x_sum_order_median_max_filtered)),
                        #     x_sum_order_median_max_filtered,
                        #     k=2,
                        #     )
                        #
                        # #   Normalize spectrum
                        # x_data = np.arange(len(x_sum_order))
                        # cont = norm_fit(x_data)
                        # x_sum_order_norm = x_sum_order / cont
                        #
                        # mask = np.argwhere(x_sum_order_norm > 1.)
                        # x_sum_order_norm[mask] = 1.
                        #
                        # print(
                        #     np.mean(x_sum_order_norm),
                        #     np.median(x_sum_order_norm),
                        #     np.var(x_sum_order_norm),
                        #     np.std(x_sum_order_norm),
                        #     )
                        #
                        # fig = plt.figure(figsize=(20, 7))
                        # ax1 = plt.subplot(1, 2, 1)
                        # ax2 = plt.subplot(1, 2, 2)
                        #
                        # ax1.plot(x_data, x_sum_order)
                        # ax1.plot(x_data, cont)
                        #
                        # ax2.plot(x_data, x_sum_order_norm)
                        #
                        # plt.show()
                        # plt.close()

                    # print(baches_spectra)
                    # print(
                    #     signal.find_peaks(
                    #         y_sum-y_sum_min,
                    #         height=y_sum_median,
                    #         width=(12, 50),
                    #         # rel_height=0.9,
                    #         )
                    #     )

                img_type_estimate = 'UK'

                if int(median) == 65535:
                    img_type_estimate = 'over_exposed'

                if (n_non_zero_histo <= 2 and
                    standard < 15 and
                    spectra_type is None):
                    # print('exptime', exptime)
                    if exptime <= 0.01:
                        img_type_estimate = 'bias'
                    else:
                        img_type_estimate = 'dark'

                # if (n_non_zero_histo >= 40 and
                elif (n_non_zero_histo >= 100 and
                    standard > 650 and
                    standard < 1400):
                    if  spectra_type == 'dados':
                        img_type_estimate = 'wave'
                    elif spectra_type == 'baches':
                        img_type_estimate = 'wave'
                    # img_type_estimate = 'th_ar'


                # if (n_non_zero_histo > 10 and
                #     n_non_zero_histo < 30 and
                #     standard > 1300):
                # elif (n_non_zero_histo > 60 and
                    # n_non_zero_histo < 180 and
                    # standard > 1300):
                elif (n_non_zero_histo > 60 and
                    spectra_type == 'baches'):
                    if median > 4000 or flux_in_orders_average > 1700:
                        # max_histo_id == 7 and
                        img_type_estimate = 'flat'
                    else:
                        img_type_estimate = 'light'

                elif (n_non_zero_histo > 60 and
                    spectra_type == 'dados'):
                    # max_histo_id == 7 and
                    img_type_estimate = 'flat'



                # elif (n_non_zero_histo > 10 and
                #       spectra_type is None):
                #         # max_histo_id == 7 and
                #         img_type_estimate = 'flat'
                #
                # # if (n_non_zero_histo >= 2 and
                # #     standard < 300):
                #     # if max_histo_id >= 7:
                # elif n_non_zero_histo >= 2:
                #     # if median > 1000:
                #     # if spectra_type == 'baches' and n_non_zero_histo <= 15:
                #     if spectra_type == 'baches':
                #         img_type_estimate = 'light_baches'
                #     # elif spectra_type == 'dados' and n_non_zero_histo <= 15:
                #     elif spectra_type == 'dados':
                #         img_type_estimate = 'light_dados'
                #     else:
                #         img_type_estimate = 'light_img'

                # elif n_non_zero_histo >= 2:
                #     if spectra_type == 'baches':
                #         img_type_estimate = 'light_baches'
                #     elif spectra_type == 'dados':
                #         img_type_estimate = 'light_dados'

                elif spectra_type in ['baches', 'dados']:
                    img_type_estimate = 'light'

                elif (standard > 1000 and
                      # max_histo_id > 200 and
                      spectra_type is None):
                        if n_non_zero_histo > 100:
                            img_type_estimate = 'light'
                        else:
                            img_type_estimate = 'flat'

                elif (standard <= 200 and
                      max_histo_id < 100 and
                      spectra_type is None):
                        img_type_estimate = 'light'

                elif (standard > 300 and
                      max_histo_id < 100 and
                      max_histo_id > 20 and
                      spectra_type is None):
                        img_type_estimate = 'flat'

                elif (standard > 200 and
                      standard < 500 and
                      n_non_zero_histo > 100 and
                      spectra_type is None):
                        img_type_estimate = 'light'

                elif (y_mid_mean_value > 10000 and spectra_type is None):
                    img_type_estimate = 'flat'


                print('Object name: ', objectname)
                print(
                  'Image type: ',
                  imagetyp,
                  '\tEstimated: ',
                  img_type_estimate,
                  '\tInstrument: ',
                  spectra_type,
                  )
                # print(histogram)
                print(
                  'Histo max position: ',
                  max_histo_id,
                  '\tNumber of non zero bins: ',
                  n_non_zero_histo,
                  # np.nonzero(histogram),
                  # len(histogram),
                  )
                print(
                  'Median = ',
                  median,
                  '\tMean = ',
                  mean,
                  '\tVariance = ',
                  variance,
                  '\tStandard deviation = ',
                  standard,
                  )
                print()

                if ((img_type_estimate != imagetyp or imagetyp == 'light') and
                    not (img_type_estimate == 'light' and imagetyp == 'wave')):
                    outfile.write(
                        f'Image type: {imagetyp}\tEstimated: {img_type_estimate}\tInstrument: {spectra_type}\n'
                        )
                    outfile.write(
                        f'File: {file_path.absolute()}\n\n'
                        )

        print('---------------------------------------------')
        print()
        outfile.write(f'-------------------------------------------------\n')

#   Model parameter:
#       instrument: baches or dados --> spectra_type
#       derived_exposure_type = bias, dark, wave, flat, light, over_exposed
#       add flag if derived_exposure_type and Header value are consistent

    outfile.close()
