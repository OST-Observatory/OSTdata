from pathlib import Path

import django

import os

from utilities import analyze_and_update_exposure_type

os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
django.setup()

from obs_run.models import DataFile

if __name__ == "__main__":
    for data_file in DataFile.objects.all():
        #   Check if the file was already analyzed
        if data_file.status_parameters == 'CLA':
            continue

        try:
            # print(data_file.datafile)
            file_path = Path(data_file.datafile)

            status, _, estimated_exposure_type, spectrum_type, _ = analyze_and_update_exposure_type(
                file_path,
                plot_histogram=False,
                print_to_terminal=True,
            )
            print(data_file.datafile)
            print(status, estimated_exposure_type, spectrum_type)
            print()

            if status:
                if estimated_exposure_type == 'bias':
                    data_file.exposure_type = 'BI'
                if estimated_exposure_type == 'dark':
                    data_file.exposure_type = 'DA'
                if estimated_exposure_type == 'flat':
                    data_file.exposure_type = 'FL'
                if estimated_exposure_type == 'light':
                    data_file.exposure_type = 'LI'

                if spectrum_type == 'dados':
                    data_file.spectrograph = 'D'
                if spectrum_type == 'baches':
                    data_file.spectrograph = 'B'
                if spectrum_type == 'einstein':
                    data_file.spectrograph = 'E'

                data_file.status_parameters = 'CLA'

                data_file.save()

        except:
            print(f"{data_file.datafile} could not be analyzed")

