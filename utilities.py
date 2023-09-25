import os
import re
from pathlib import Path

import numpy as np

from astroquery.simbad import Simbad
from astropy.coordinates.angles import Angle
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.io import fits
from astropy.time import Time
from astropy.visualization import simple_norm

from scipy import ndimage, signal

import matplotlib.pyplot as plt

import django
from django.db.models import F, ExpressionWrapper, DecimalField

os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
django.setup()

from objects.models import Object
from obs_run.models import ObservationRun, DataFile


def add_new_observation_run(data_path, print_to_terminal=False,
                            add_data_files=False):
    """
    Adds new observation run and all associated objects and datasets
    if requested

    Parameters
    ----------
    data_path           : `pathlib.Path`
        Path to the directory with the observation data

    print_to_terminal   : `boolean`, optional
        If True information will be printed to the terminal.
        Default is ``False``.

    add_data_files      : `boolean`, optional
        If True also data files and objects will be added to the database.
        Default is ``False``.
    """
    #   Regular expression definitions for allowed directory name
    rex1 = re.compile("^[0-9]{8}$")
    rex2 = re.compile("^[0-9]{4}.[0-9]{2}.[0-9]{2}$")

    #   Get name of observation run
    basename = data_path.name
    if rex1.match(basename) or rex2.match(basename):
        #   Create new run
        new_observation_run = ObservationRun(
            name=basename,
            reduction_status='NE',
        )
        new_observation_run.save()
        if print_to_terminal:
            print('Run: ', basename)

        #   Process data files
        if add_data_files:
            for (root, dirs, files) in os.walk(data_path, topdown=True):
                for f in files:
                    file_path = Path(root, f)
                    successful = add_new_data_file(
                        file_path,
                        new_observation_run,
                        print_to_terminal=print_to_terminal
                    )
                    if not successful:
                        continue

            #   Set time of observation run -> mid of observation
            datafiles = new_observation_run.datafile_set.filter(
                hjd__gt=2451545
            )
            start_jd = datafiles.order_by('hjd')
            # print(start_jd)
            if not start_jd:
                new_observation_run.mid_observation_jd = 0.
            else:
                start_jd = start_jd[0].hjd
                end_jd = datafiles.order_by('hjd').reverse()
                if not end_jd:
                    new_observation_run.mid_observation_jd = start_jd
                else:
                    end_jd = end_jd[0].hjd
                    new_observation_run.mid_observation_jd = start_jd + (end_jd - start_jd) / 2.
            new_observation_run.save()
            if print_to_terminal:
                print('----------------------------------------')
                print()


def add_new_data_file(path_to_file, observation_run, print_to_terminal=False):
    """
    Adds new dataset and associated objects

    Parameters
    ----------
    path_to_file                : `pathlib.Path`
        Path to the data file

    observation_run             : `obs_run.models.ObservationRun`
        Observation run to which the data file belongs

    print_to_terminal           : `boolean`, optional
        If True information will be printed to the terminal.
        Default is ``False``.

    Returns
    -------
                                : `boolean`
        Returns True if data files and objects were added successfully.
    """
    if print_to_terminal:
        print('File: ', path_to_file.absolute())

    suffix = path_to_file.suffix
    if suffix in ['.fit', '.fits', '.FIT', '.FITS']:
        file_type = 'FITS'
    elif suffix in ['.CR2', '.cr2']:
        file_type = 'CR2'
    elif suffix in ['.JPG', '.jpg', '.jpeg', '.JPEG']:
        file_type = 'JPG'
    elif suffix in ['.tiff', '.tif', '.TIF', '.TIFF']:
        file_type = 'TIFF'
    elif suffix in ['.ser', '.SER']:
        file_type = 'SER'
    else:
        return False

    data_file = DataFile(
        observation_run=observation_run,
        datafile=path_to_file.absolute(),
        file_type=file_type,
    )
    data_file.save()

    #   Evaluate data file
    evaluate_data_file(
        data_file,
        observation_run,
        print_to_terminal=print_to_terminal,
    )

    return True


def evaluate_data_file(data_file, observation_run, print_to_terminal=False):
    """
    Evaluate data file and add associated objects

    Parameters
    ----------
    data_file           : `obs_run.models.DataFile`
        DataFile object

    observation_run             : `obs_run.models.ObservationRun`
        Observation run to which the data file belongs

    print_to_terminal           : `boolean`, optional
        If True information will be printed to the terminal.
        Default is ``False``.
    """
    #   Set data file information from file header data
    data_file.set_info()

    target = data_file.main_target
    expo_type = data_file.exposure_type

    #   Define special targets
    special_targets = [
        'Autosave Image', 'calib', 'mosaic', 'ThAr',
    ]
    solar_system = [
        'Sun', 'sun', 'Mercury', 'mercury', 'Venus', 'venus', 'Moon', 'moon',
        'Mond', 'mond', 'Mars', 'mars', 'Jupiter', 'jupiter', 'Saturn',
        'saturn', 'Uranus', 'uranus', 'Neptun', 'neptun', 'Pluto', 'pluto',
    ]

    #   Look for associated objects
    if (
            target != '' and
            target != 'Unknown' and
            expo_type == 'LI' and
            'flat' not in target and
            'dark' not in target and
            data_file.ra != 0. and
            data_file.dec != 0.
    ):

        #   Tolerance in degree
        # t = 0.1
        t = 0.5
        if ('20210224' in str(data_file.datafile) or
                '20220106' in str(data_file.datafile)):
            t = 1.0

        if target in special_targets or target in solar_system:
            objs = Object.objects \
                .filter(name__icontains=target)
        else:
            objs = Object.objects \
                .filter(ra__range=(data_file.ra - t, data_file.ra + t)) \
                .filter(dec__range=(data_file.dec - t, data_file.dec + t))
            # .filter(name__icontains=target) \
        if len(objs) > 0:
            if print_to_terminal:
                print('Object already known...')
            #   If there is one or more objects returned,
            #   select the closest object
            obj = objs.annotate(
                distance=ExpressionWrapper(
                    ((F('ra') - data_file.ra) ** 2 +
                     (F('dec') - data_file.dec) ** 2
                     ) ** (1. / 2.),
                    output_field=DecimalField()
                )
            ).order_by('distance')[0]
            obj.datafiles.add(data_file)
            obj.observation_run.add(observation_run)
            obj.is_main = True

            #   Update JD the object was first observed
            if (obj.first_hjd == 0. or
                    obj.first_hjd > data_file.hjd):
                obj.first_hjd = data_file.hjd

            obj.save()

            #   Set datafile target name to Simbad resolved name
            if obj.simbad_resolved:
                data_file.main_target = obj.name
                data_file.save()

            #   Add header name as an alias
            identifiers = obj.identifier_set.filter(
                name__exact=target
            )
            if len(identifiers) == 0:
                obj.identifier_set.create(
                    name=target,
                    info_from_header=True,
                )

        #   Handling of Solar system objects
        elif target in solar_system:
            #     Make a new object
            obj = Object(
                name=target,
                ra=data_file.ra,
                dec=data_file.dec,
                object_type='SO',
                simbad_resolved=False,
                first_hjd=data_file.hjd,
                is_main=True,
            )
            obj.save()
            obj.observation_run.add(observation_run)
            obj.datafiles.add(data_file)
            obj.save()

        #   Handling of special targets
        elif target in special_targets:
            #     Make a new object
            obj = Object(
                name=target,
                ra=data_file.ra,
                dec=data_file.dec,
                object_type='UK',
                simbad_resolved=False,
                first_hjd=data_file.hjd,
            )
            obj.save()
            obj.observation_run.add(observation_run)
            obj.datafiles.add(data_file)
            obj.save()
        else:
            if print_to_terminal:
                print('New object')
            #   Set Defaults
            object_ra = data_file.ra
            object_dec = data_file.dec
            object_type = 'UK'
            object_simbad_resolved = False
            object_name = target

            #   Query Simbad for object name
            custom_simbad = Simbad()
            custom_simbad.add_votable_fields(
                'otypes',
                'ids',
            )
            simbad_tbl = custom_simbad.query_object(target)

            #   Get Simbad coordinates
            if simbad_tbl is not None and len(simbad_tbl) > 0:
                simbad_ra = Angle(
                    simbad_tbl[0]['RA'],
                    unit='hour',
                ).degree
                simbad_dec = Angle(
                    simbad_tbl[0]['DEC'],
                    unit='degree',
                ).degree

                # #   Tolerance in degree
                # tol = 0.5
                # tol = 1.

                if (simbad_ra + t > data_file.ra > simbad_ra - t and
                        simbad_dec + t > data_file.dec > simbad_dec - t):
                    object_ra = simbad_ra
                    object_dec = simbad_dec
                    object_simbad_resolved = True
                    object_data_table = simbad_tbl[0]

            #   Search Simbad based on coordinates
            if not object_simbad_resolved:
                simbad_region_query = Simbad()
                simbad_region_query.add_votable_fields(
                    'otypes',
                    'ids',
                    'distance_result',
                    # 'uvby',
                    'flux(V)',
                )
                result_table = simbad_region_query.query_region(
                    SkyCoord(
                        data_file.ra * u.deg,
                        data_file.dec * u.deg,
                        frame='icrs',
                    ),
                    radius='0d5m0s',
                )

                if (result_table is not None and
                        len(result_table) > 0):

                    #   Get the brightest object if magnitudes
                    #   are available otherwise use the object
                    #   with the smallest distance to the
                    #   coordinates
                    if np.all(result_table['FLUX_V'].mask):
                        index = 0
                    else:
                        index = np.argmin(
                            result_table['FLUX_V'].data
                        )
                    simbad_ra = Angle(
                        result_table[index]['RA'],
                        unit='hour',
                    ).degree
                    simbad_dec = Angle(
                        result_table[index]['DEC'],
                        unit='degree',
                    ).degree
                    object_ra = simbad_ra
                    object_dec = simbad_dec
                    object_simbad_resolved = True
                    object_data_table = result_table[index]

            #   Set object type based on Simbad
            if object_simbad_resolved:
                object_types = object_data_table['OTYPES']

                #   Decode information in object string to
                #   get a rough object estimate
                if 'ISM' in object_types or 'PN' in object_types:
                    object_type = 'NE'
                elif 'Cl*' in object_types or 'As*' in object_types:
                    object_type = 'SC'
                elif 'G' in object_types:
                    object_type = 'GA'
                elif '*' in object_types:
                    object_type = 'ST'

                #   Set default name
                object_name = object_data_table['MAIN_ID']

            #     Make a new object
            obj = Object(
                name=object_name,
                ra=object_ra,
                dec=object_dec,
                object_type=object_type,
                simbad_resolved=object_simbad_resolved,
                first_hjd=data_file.hjd,
                is_main=True,
            )
            obj.save()
            obj.observation_run.add(observation_run)
            obj.datafiles.add(data_file)
            obj.save()

            #   Set alias names
            if object_simbad_resolved:
                #   Add header name as an alias
                obj.identifier_set.create(
                    name=target,
                    info_from_header=True,
                )

                #   Get aliases from Simbad
                aliases = object_data_table['IDS'].split('|')
                # print(aliases)

                #   Create Simbad link
                sanitized_name = object_name.replace(" ", "") \
                    .replace('+', "%2B")
                simbad_href = f"https://simbad.u-strasbg.fr/" \
                              f"simbad/sim-id?Ident=" \
                              f"{sanitized_name}"

                #   Set identifier objects
                for alias in aliases:
                    obj.identifier_set.create(
                        name=alias,
                        href=simbad_href,
                    )

                #   Set datafile target name to Simbad resolved
                #   name
                data_file.main_target = object_name
                data_file.save()

        if print_to_terminal:
            print()


def analyze_and_update_exposure_type(file_path, plot_histogram=False,
                                     print_to_terminal=False):
    """
    Estimate exposure type (bias, dark, flat, light) and observation type
    (photometry, spectroscopy)

    Parameters
    ----------
    file_path               : `pathlib.Path`
        Path to the file to be analyzed

    plot_histogram          : `boolean`, optional
        If True the histogram of the image will be plotted.

    print_to_terminal       : `boolean`, optional
        If True information will be printed to the terminal.
        Default is ``False``.

    Returns
    -------
                            : `boolean`
        True if image and spectrum type were estimated.

    image_type_fits         : `string`
        Image type from FITS header.

    estimated_image_type    : `string`
        Estimated image type

    spectrum_type           : `string`
        Spectrum type. None for photometric observations.

    instrument              : `string`
        Instrument from FITS header
    """

    jd_start_stf8300 = Time('2015-02-01T00:00:00.00', format='fits').jd

    suffix = file_path.suffix
    if suffix in ['.fit', '.fits', '.FIT', '.FITS']:
        if print_to_terminal:
            print('File: ', file_path.absolute())

        header = fits.getheader(file_path, 0)

        image_type_fits = header.get('IMAGETYP', 'UK')
        if image_type_fits == 'Flat Field':
            image_type_fits = 'flat'
        if image_type_fits == 'Dark Frame':
            image_type_fits = 'dark'
        if image_type_fits == 'Light Frame':
            image_type_fits = 'light'
        if image_type_fits == 'Bias Frame':
            image_type_fits = 'bias'
        objectname = header.get('OBJECT', 'UK')
        exptime = header.get('EXPTIME', -1)
        instrument = header.get('INSTRUME', '-')
        naxis1 = header.get('NAXIS1', 1)
        binning = header.get('XBINNING', 1)
        # img_filter = header.get('FILTER', '-')
        obs_time = header.get('DATE-OBS', '2000-01-01T00:00:00.00')
        jd = Time(obs_time, format='fits').jd
        rgb = header.get('BAYERPAT', None)

        n_pix_x = naxis1 * binning

        image_data_original = fits.getdata(file_path, 0)

        img_shape = image_data_original.shape
        # print(image_data_original.shape)
        # print(image_data_original.ndim)

        if image_data_original.ndim != 2:
            return False, None, None, None, None

        image_data = ndimage.median_filter(image_data_original, size=10)

        if plot_histogram:
            plt.figure(figsize=(20, 7))
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
        print('y_mid_mean_value =', y_mid_mean_value)

        y_sum_min = np.min(y_sum)
        # y_sum_mean = np.mean(y_sum)
        # y_sum_mean = np.mean(y_sum-y_sum_min)
        y_sum_median = np.median(y_sum - y_sum_min)
        # y_sum_standard = np.std(y_sum)

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

        # x_sum = np.sum(image_data_original, axis=0)
        # x_sum_min = np.min(x_sum)
        # x_sum_median = np.median(x_sum-x_sum_min)
        # x_sum_standard = np.std(x_sum)

        spectrum_type = None
        flux_in_orders_average = None

        if (instrument != 'SBIG STF-8300'
                and n_pix_x < 9000
                and not (instrument in ['SBIG ST-8 3 CCD Camera', 'SBIG ST-8'] and jd < jd_start_stf8300)):

            einstein_spectra_broad = signal.find_peaks(
                y_sum - y_sum_min,
                height=y_sum_median,
                # height=y_sum_mean,
                width=(1110, 1130),
                # rel_height=0.5,
            )
            print('einstein_spectra_broad:')
            print(einstein_spectra_broad)
            einstein_spectra_narrow = signal.find_peaks(
                y_sum - y_sum_min,
                height=y_sum_median,
                # height=y_sum_mean,
                width=(775, 795),
                # rel_height=0.5,
            )
            print('einstein_spectra_narrow:')
            print(einstein_spectra_narrow)

            einstein_spectra_half = signal.find_peaks(
                y_sum - y_sum_min,
                height=y_sum_median,
                width=(370, 385),
            )
            print('einstein_spectra_half:')
            print(einstein_spectra_half)

            # print(
            #     signal.find_peaks(
            #         y_sum,
            #         # y_sum-y_sum_min,
            #         height=y_sum_standard,
            #         # width=(110, 160),
            #         # width=110,
            #         width=(130, 190),
            #         # rel_height=0.9,
            #         rel_height=1.0,
            #         distance=4.,
            #         )
            # )
            # print(
            #     signal.find_peaks(
            #         # x_sum-x_sum_min,
            #         x_sum,
            #         height=x_sum_standard,
            #         width=int(naxis1 * 0.5),
            #         rel_height=0.9,
            #         )
            # )
            # print('======')
            # print(
            #     signal.find_peaks(
            #         y_sum-y_sum_min,
            #         height=y_sum_median,
            #         # height=y_sum_mean,
            #         width=(1110, 1130),
            #         # rel_height=0.5,
            #         )
            # )
            if (einstein_spectra_broad[0].size >= 1
                    or einstein_spectra_narrow[0].size >= 1
                    or einstein_spectra_half[0].size == 2):
                spectrum_type = 'einstein'
                # print(dados_spectra)
            else:
                dados_spectra = signal.find_peaks(
                    y_sum - y_sum_min,
                    height=y_sum_median,
                    # height=y_sum_mean,
                    width=(132, 139),
                    rel_height=0.9,
                    prominence=30000.,
                )
                print('dados_spectra:')
                print(dados_spectra)

                dados_peaks = signal.find_peaks(
                    y_sum - y_sum_min,
                    height=y_sum_median,
                    # height=y_sum_mean,
                    # width=(110, 160),
                    # width=110,
                    width=(10, 50),
                    # width=(130, 190),
                    # width=(132, 139),
                    rel_height=0.9,
                    # rel_height=0.9,
                    # rel_height=1.0,
                )
                print('dados_peaks:')
                print(dados_peaks)
                spectrum_detected = False
                if 1 < dados_peaks[0].size < 16:
                    smallest_peak = np.min(dados_peaks[1]['peak_heights'])
                    largest_peak = np.max(dados_peaks[1]['peak_heights'])
                    if largest_peak > 5 * smallest_peak:
                        spectrum_detected = True

                if (dados_spectra[0].size > 1 or
                        (instrument == 'SBIG ST-7' and dados_spectra[0].size) or
                        (instrument in ['SBIG ST-7', 'SBIG ST-8 3 CCD Camera', 'SBIG ST-8']
                         and spectrum_detected)):
                    spectrum_type = 'dados'
                    # print(dados_spectra)
                else:
                    # print(
                    #     signal.find_peaks(
                    #         y_sum-y_sum_min,
                    #         height=y_sum_median,
                    #         # height=y_sum_mean,
                    #         # width=(110, 160),
                    #         # width=110,
                    #         width=(100, 150),
                    #         # width=(132, 139),
                    #         rel_height=0.9,
                    #         # rel_height=1.0,
                    #         )
                    # )

                    baches_spectra = signal.find_peaks(
                        y_sum - y_sum_min,
                        height=y_sum_median,
                        # width=(16, 30),
                        width=(16, 50),
                        # rel_height=0.9,
                        # prominence=30000.,
                        prominence=10000.,
                    )

                    n_order = baches_spectra[0].size

                    jd_pre_baches = Time(
                        '2014-12-08T00:00:00.00',
                        format='fits'
                    ).jd
                    if n_order >= 4 and jd > jd_pre_baches:
                        spectrum_type = 'baches'
                        print('baches_spectra:')
                        print(baches_spectra)
                        # print(baches_spectra[-1])
                        # print(baches_spectra[-1]['right_ips'])

                        x_sum_order = 0.
                        n_pixel_in_orders = 0
                        for i in range(0, n_order):
                            start_order = int(baches_spectra[-1]['left_ips'][i])
                            end_order = int(baches_spectra[-1]['right_ips'][i])

                            x_sum_order += np.sum(
                                image_data_original[start_order:end_order, :]
                            )
                            n_pixel_in_orders += ((end_order - start_order)
                                                  * img_shape[1])

                        flux_in_orders_average = x_sum_order / n_pixel_in_orders
                        print(flux_in_orders_average, n_pixel_in_orders)

        estimated_image_type = 'UK'

        if np.isnan(median) or int(median) == 65535:
            estimated_image_type = 'over_exposed'

        elif (n_non_zero_histo <= 2 and
              standard < 15 and
              # not (instrument == 'QHYCCD-Cameras-Capture' and median > 50) and
              spectrum_type is None):
            # print('exptime', exptime)
            if exptime <= 0.01:
                estimated_image_type = 'bias'
            else:
                estimated_image_type = 'dark'

        elif instrument == 'SBIG ST-i CCD Camera':
            estimated_image_type = 'light'

        elif spectrum_type == 'dados':
            if instrument == 'SBIG ST-7':
                if n_non_zero_histo >= 350:
                    if standard > 11000:
                        estimated_image_type = 'flat'
                    else:
                        estimated_image_type = 'light'
                elif n_non_zero_histo >= 90:
                    if median > 600:
                        estimated_image_type = 'wave'
                    else:
                        estimated_image_type = 'light'
                else:
                    if standard > 670:
                        estimated_image_type = 'light'
                    else:
                        estimated_image_type = 'wave'

            else:
                if n_non_zero_histo >= 300:
                    if standard > 10000:
                        estimated_image_type = 'flat'
                    else:
                        estimated_image_type = 'light'
                elif (n_non_zero_histo >= 100 and
                      600 < standard < 1900):
                    estimated_image_type = 'wave'

                elif n_non_zero_histo > 60:
                    if standard < 220:
                        estimated_image_type = 'light'
                    elif 700 < standard > 6000:
                        estimated_image_type = 'flat'
                    else:
                        estimated_image_type = 'wave'

                elif n_non_zero_histo > 40 and standard > 6000:
                    estimated_image_type = 'flat'

                elif n_non_zero_histo > 35 and standard > 280:
                    estimated_image_type = 'wave'

                else:
                    estimated_image_type = 'light'

        elif spectrum_type == 'baches':
            if (n_non_zero_histo >= 110 and
                    300 < standard < 1500):
                estimated_image_type = 'wave'

            # elif n_non_zero_histo > 60:
            elif n_non_zero_histo > 40:
                if median > 4000 or flux_in_orders_average > 1900:
                    # max_histo_id == 7 and
                    estimated_image_type = 'flat'
                else:
                    estimated_image_type = 'light'

            elif n_non_zero_histo >= 25:
                if standard > 550:
                    # max_histo_id == 7 and
                    estimated_image_type = 'flat'
                else:
                    estimated_image_type = 'light'

            else:
                estimated_image_type = 'light'

        elif spectrum_type == 'einstein':
            estimated_image_type = 'light'

        else:
            if rgb is not None:
                estimated_image_type = 'rgb'

            if standard > 1000:
                if n_non_zero_histo > 100 and y_mid_mean_value < 10000:
                    estimated_image_type = 'light'
                else:
                    estimated_image_type = 'flat'

            elif standard <= 200 and max_histo_id < 100:
                estimated_image_type = 'light'

            elif (standard > 300 and
                  100 > max_histo_id > 20):
                estimated_image_type = 'flat'

            elif (200 < standard < 500 and
                  n_non_zero_histo > 100):
                estimated_image_type = 'light'

            elif y_mid_mean_value > 10000:
                estimated_image_type = 'flat'

        if print_to_terminal:
            print('Object name: ', objectname)
            print(
                'Image type: ',
                image_type_fits,
                '\tEstimated: ',
                estimated_image_type,
                '\tSpectra type: ',
                spectrum_type,
                '\tInstrument: ',
                instrument,
            )
            # print(histogram)
            print(
                'Histo max position: ',
                max_histo_id,
                '\tNumber of non zero bins: ',
                n_non_zero_histo,
                # np.nonzero(histogram),
                # len(histogram),
                '\tAverage flux in orders: ',
                flux_in_orders_average,
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

        return True, image_type_fits, estimated_image_type, spectrum_type, instrument
    else:
        return False, None, None, None, None
