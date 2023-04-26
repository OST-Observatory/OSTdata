import sys
import os
os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
import re
from pathlib import Path, PurePath

import numpy as np

from astroquery.simbad import Simbad
from astropy.coordinates.angles import Angle
from astropy.coordinates import SkyCoord
import astropy.units as u

import django
django.setup()
from django.db.models import F, ExpressionWrapper, DecimalField

from objects.models import Object, Identifier
from obs_run.models import Obs_run, DataFile

if __name__ == "__main__":
    #   Special targets
    special_taget = [
        'Autosave Image', 'calib', 'mosaic', 'ThAr',
        ]
    solar_system = [
        'Sun', 'sun', 'Mercury', 'mercury', 'Venus', 'venus', 'Moon', 'moon',
        'Mond', 'mond', 'Mars', 'mars', 'Jupiter', 'jupiter', 'Saturn',
        'saturn', 'Uranus', 'uranus', 'Neptun', 'neptun', 'Pluto', 'pluto',
        ]

    #   Delete all Observation runs and DataFile entries in the database
    for run in Obs_run.objects.all():
        run.delete()

    for f in DataFile.objects.all():
        f.delete()

    for o in Object.objects.all():
        o.delete()

    #   Input path
    data_path = sys.argv[1]
    # data_path = 'test_data'
    data_path = Path(data_path)

    #   Regular expression definitions for allowed directory name
    rex1 = re.compile("^[0-9]{8}$")
    rex2 = re.compile("^[0-9]{4}.[0-9]{2}.[0-9]{2}$")

    #   Load data and setup models
    for run in data_path.iterdir():
        basename = run.name
        if rex1.match(basename) or rex2.match(basename):
            #   Create new run
            new_run = Obs_run(
                name=basename,
                reduction_status='NE',
                )
            new_run.save()
            print('Run: ', basename)

            #   List data files
            for (root,dirs,files) in os.walk(run, topdown=True):
                for f in files:
                    file_path = Path(root, f)
                    print('File: ', file_path.absolute())

                    suffix = file_path.suffix
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
                        continue

                    data_file = DataFile(
                        obsrun=new_run,
                        datafile=file_path.absolute(),
                        file_type=file_type,
                        )
                    data_file.save()
                    data_file.set_infos()

                    target = data_file.main_target
                    expo_type = data_file.exposure_type

                    if (
                        target != '' and
                        target != 'Unknown' and
                        expo_type == 'LI' and
                        'flat' not in target and
                        'dark' not in target
                        ):

                        #   Tolerance in degree
                        t = 0.1
                        t = 0.5

                        if target in special_taget or target in solar_system:
                            objs = Object.objects \
                                .filter(name__icontains=target)
                        else:
                            objs = Object.objects \
                                .filter(
                                    ra__range=(data_file.ra-t, data_file.ra+t)
                                    ) \
                                .filter(
                                    dec__range=(data_file.dec-t, data_file.dec+t)
                                    )
                                # .filter(name__icontains=target) \

                        if len(objs) > 0:
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
                            obj.obsrun.add(new_run)
                            obj.is_main = True
                            obj.save()

                        #   Handling of Solar system objects
                        elif target in solar_system:
                            #     Make a new object
                            obj = Object(
                                name=target,
                                ra=data_file.ra,
                                dec=data_file.dec,
                                object_type='SO',
                                simbad_resolved=False,
                            )
                            obj.save()
                            obj.obsrun.add(new_run)
                            obj.datafiles.add(data_file)
                            obj.save()

                        #   Handling of special targets
                        elif target in special_taget:
                            #     Make a new object
                            obj = Object(
                                name=target,
                                ra=data_file.ra,
                                dec=data_file.dec,
                                object_type='UK',
                                simbad_resolved=False,
                            )
                            obj.save()
                            obj.obsrun.add(new_run)
                            obj.datafiles.add(data_file)
                            obj.save()
                        else:
                            print('New object')
                            #   Set Defaults
                            object_ra = data_file.ra
                            object_dec = data_file.dec
                            object_type = 'UK'
                            object_simbad_resolved = False
                            object_name = target

                            #   Query Simbad for object name
                            customSimbad = Simbad()
                            customSimbad.add_votable_fields(
                                'otypes',
                                'ids',
                                )
                            simbad_tbl = customSimbad.query_object(target)

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

                                #   Tolerance in degree
                                tol = 1.

                                if (data_file.ra < simbad_ra + tol and
                                    data_file.ra > simbad_ra - tol and
                                    data_file.dec < simbad_dec + tol and
                                    data_file.dec > simbad_dec - tol):
                                    object_ra = simbad_ra
                                    object_dec = simbad_dec
                                    object_simbad_resolved = True
                                    object_data_table = simbad_tbl[0]

                            #   Search Simbad based on coordinates
                            if not object_simbad_resolved:
                                regionSimbad = Simbad()
                                regionSimbad.add_votable_fields(
                                    'otypes',
                                    'ids',
                                    'distance_result',
                                    # 'uvby',
                                    'flux(V)',
                                    )
                                result_table = regionSimbad.query_region(
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
                                otypes = object_data_table['OTYPES']

                                #   Decode information in object string to
                                #   get a rough object estimate
                                if 'ISM' in otypes or 'PN' in otypes:
                                    object_type = 'NE'
                                elif 'Cl*' in otypes or 'As*' in otypes:
                                    object_type = 'SC'
                                elif 'G' in otypes:
                                    object_type = 'GA'
                                elif '*' in otypes:
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
                            )
                            obj.save()
                            obj.obsrun.add(new_run)
                            obj.datafiles.add(data_file)
                            obj.save()


                            #   Set alias names
                            if object_simbad_resolved:
                                #   Add own alias
                                obj.identifier_set.create(name=target)

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

                        print()
            print('----------------------------------------')
            print()
