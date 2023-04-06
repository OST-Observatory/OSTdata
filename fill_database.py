import sys
import os
os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
import re
from pathlib import Path, PurePath
import django
django.setup()
from django.db.models import F, ExpressionWrapper, DecimalField
from objects.models import Object
from obs_run.models import Obs_run, DataFile

if __name__ == "__main__":
    #   Special targets
    special_taget = [
        'Sun', 'sun', 'Mercury', 'mercury', 'Venus', 'venus', 'Moon', 'moon',
        'Mond', 'mond', 'Mars', 'mars', 'Jupiter', 'jupiter', 'Saturn',
        'saturn', 'Uranus', 'uranus', 'Neptun', 'neptun', 'Pluto', 'pluto',
        '	Autosave Image', 'calib', 'mosaic', 'ThAr',
        ]

    #   Delete all Observation runs and DataFile entries in the database
    for run in Obs_run.objects.all():
        run.delete()

    for f in DataFile.objects.all():
        f.delete()

    for o in Object.objects.all():
        o.delete()

    #   Input path
    data_path = 'test_data'
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

                        if target in special_taget:
                            objs = Object.objects \
                                .filter(name__icontains=target)
                        else:
                            objs = Object.objects \
                                .filter(name__icontains=target) \
                                .filter(
                                    ra__range=(data_file.ra-t, data_file.ra+t)
                                    ) \
                                .filter(
                                    dec__range=(data_file.dec-t, data_file.dec+t)
                                    )

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
                        else:
                            print('New object')
                            #     Need to make a new star
                            obj = Object(
                                name=target,
                                ra=data_file.ra,
                                dec=data_file.dec,
                            )
                            obj.save()
                            obj.obsrun.add(new_run)
                            obj.datafiles.add(data_file)
                            obj.save()
                        print()
            print('----------------------------------------')
            print()
