"""
ML-based exposure type classification service.

This module provides a service for classifying DataFile exposure types using
a trained Keras model from the ost_image_classification package.
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# Try to import the classification service
try:
    from inference_runner import ClassifierService
    CLASSIFIER_AVAILABLE = True
except ImportError:
    CLASSIFIER_AVAILABLE = False
    logger.warning(
        'ost_image_classification package not available. '
        'Install with: pip install git+https://github.com/OST-Observatory/ost_image_classification.git@main'
    )

from .models import DataFile


class ExposureTypeClassifier:
    """
    Service class for ML-based exposure type classification.
    
    Uses a singleton pattern for lazy model loading.
    """
    _instance = None
    _classifier = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ExposureTypeClassifier, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self._classifier = None

    def _ensure_initialized(self):
        """Initialize the classifier service if not already done."""
        if self._classifier is not None:
            return

        if not CLASSIFIER_AVAILABLE:
            raise ImproperlyConfigured(
                'ost_image_classification package is not installed. '
                'Install with: pip install git+https://github.com/OST-Observatory/ost_image_classification.git@main'
            )

        if not getattr(settings, 'ML_EXPOSURE_TYPE_ENABLED', False):
            raise ImproperlyConfigured('ML_EXPOSURE_TYPE_ENABLED is False in settings')

        model_path = getattr(settings, 'ML_EXPOSURE_TYPE_MODEL_PATH', None)
        if not model_path:
            raise ImproperlyConfigured('ML_EXPOSURE_TYPE_MODEL_PATH is not set in settings')

        model_path = Path(model_path)
        if not model_path.exists():
            raise ImproperlyConfigured(f'Model file not found: {model_path}')

        thresholds_path = getattr(settings, 'ML_EXPOSURE_TYPE_THRESHOLDS_PATH', None)
        if thresholds_path:
            thresholds_path = Path(thresholds_path)
            if not thresholds_path.exists():
                logger.warning(f'Thresholds file not found: {thresholds_path}, continuing without it')
                thresholds_path = None

        try:
            # Initialize ClassifierService with configuration from settings
            temperature = getattr(settings, 'ML_EXPOSURE_TYPE_TEMPERATURE', 0.7)
            tta = getattr(settings, 'ML_EXPOSURE_TYPE_TTA', False)
            abstain_unknown = getattr(settings, 'ML_EXPOSURE_TYPE_ABSTAIN_UNKNOWN', True)
            target_size = getattr(settings, 'ML_EXPOSURE_TYPE_TARGET_SIZE', [448, 448])
            
            # Convert target_size to tuple if it's a list
            if isinstance(target_size, list):
                target_size = tuple(target_size)

            self._classifier = ClassifierService(
                model_path=str(model_path),
                thresholds_path=str(thresholds_path) if thresholds_path else None,
                temperature=temperature,
                tta=tta,
                abstain_unknown=abstain_unknown,
                target_size=target_size,
            )
            logger.info(f'ML Exposure Type Classifier initialized with model: {model_path}')
        except Exception as e:
            logger.error(f'Failed to initialize ML Exposure Type Classifier: {e}', exc_info=True)
            raise

    def is_supported_format(self, file_type: str, file_path: Optional[Path] = None) -> bool:
        """
        Check if the file format is supported for ML classification.
        
        Parameters
        ----------
        file_type : str
            File type string (e.g., 'FITS', 'TIFF')
        file_path : Path, optional
            File path for additional format detection if needed
        
        Returns
        -------
        bool
            True if format is supported
        """
        supported_formats = getattr(settings, 'ML_EXPOSURE_TYPE_SUPPORTED_FORMATS', ['FITS', 'TIFF'])
        return file_type.upper() in [f.upper() for f in supported_formats]

    def _map_model_class_to_exposure_type_and_spectrograph(self, model_class: str) -> tuple:
        """
        Map model output class names to DataFile exposure type codes and spectrograph.
        
        Parameters
        ----------
        model_class : str
            Class name from the model (e.g., 'bias', 'darks', 'flat_dados', 'spectrum_baches')
        
        Returns
        -------
        tuple
            (exposure_type_code, spectrograph_code)
            exposure_type_code: str (BI, DA, FL, LI, WA, UK)
            spectrograph_code: str (D, B, E, N)
        """
        # Normalize class name (lowercase, strip whitespace)
        normalized_class = model_class.lower().strip()
        
        # Mapping: (exposure_type, spectrograph)
        mapping = {
            'bias': (DataFile.BIAS, 'N'),
            'darks': (DataFile.DARK, 'N'),
            'flats': (DataFile.FLAT, 'N'),
            'flat_dados': (DataFile.FLAT, 'D'),
            'flat_baches': (DataFile.FLAT, 'B'),
            'deep_sky': (DataFile.LIGHT, 'N'),
            'spectrum_dados': (DataFile.LIGHT, 'D'),
            'spectrum_baches': (DataFile.LIGHT, 'B'),
            'wavelength_calibration_dados': (DataFile.WAVE, 'D'),
            'wavelength_calibration_baches': (DataFile.WAVE, 'B'),
            'einsteinturm': (DataFile.LIGHT, 'E'),
            'unknown': (DataFile.UNKNOWN, 'N'),
        }
        
        return mapping.get(normalized_class, (DataFile.UNKNOWN, 'N'))

    def classify_datafile(self, datafile: DataFile) -> Dict:
        """
        Classify a single DataFile instance.
        
        Parameters
        ----------
        datafile : DataFile
            DataFile instance to classify
        
        Returns
        -------
        dict
            Dictionary with keys:
            - 'exposure_type_ml': str (exposure type code)
            - 'exposure_type_ml_confidence': float (confidence score 0.0-1.0)
            - 'exposure_type_ml_abstained': bool (whether model abstained)
            - 'spectrograph_ml': str (spectrograph code: D, B, E, N)
            - 'error': str (error message if classification failed)
        """
        if not self.is_supported_format(datafile.file_type, Path(datafile.datafile)):
            return {
                'exposure_type_ml': None,
                'exposure_type_ml_confidence': None,
                'exposure_type_ml_abstained': False,
                'spectrograph_ml': None,
                'error': f'Unsupported file format: {datafile.file_type}',
            }

        try:
            self._ensure_initialized()
        except Exception as e:
            return {
                'exposure_type_ml': None,
                'exposure_type_ml_confidence': None,
                'exposure_type_ml_abstained': False,
                'spectrograph_ml': None,
                'error': str(e),
            }

        file_path = Path(datafile.datafile)
        if not file_path.exists():
            return {
                'exposure_type_ml': None,
                'exposure_type_ml_confidence': None,
                'exposure_type_ml_abstained': False,
                'error': f'File not found: {file_path}',
            }

        try:
            # Call the classifier service - predict_paths expects a list
            file_path_str = str(file_path)
            batch_result = self._classifier.predict_paths([file_path_str], batch_size=1)
            
            # Extract classification result from batch results
            # predict_paths returns: {"meta": {...}, "results": [...], "defects": [...], "warnings": [...]}
            results = batch_result.get('results', [])
            if not results:
                # Check for errors in defects
                defects = batch_result.get('defects', [])
                if defects:
                    error_msg = defects[0].get('message', 'Unknown error')
                    return {
                        'exposure_type_ml': None,
                        'exposure_type_ml_confidence': None,
                        'exposure_type_ml_abstained': False,
                        'spectrograph_ml': None,
                        'error': error_msg,
                    }
                return {
                    'exposure_type_ml': None,
                    'exposure_type_ml_confidence': None,
                    'exposure_type_ml_abstained': False,
                    'spectrograph_ml': None,
                    'error': 'No results returned from classifier',
                }
            
            # Get the first (and only) result
            result = results[0]
            
            # Check for error in result
            if 'error' in result:
                return {
                    'exposure_type_ml': None,
                    'exposure_type_ml_confidence': None,
                    'exposure_type_ml_abstained': False,
                    'spectrograph_ml': None,
                    'error': result['error'],
                }
            
            # Extract classification result
            # Expected format from ClassifierService.predict_paths:
            # - result['class']: predicted class name
            # - result['score']: confidence score (0.0-1.0)
            # - result['abstained']: bool (if model abstained)
            
            predicted_class = result.get('class', 'unknown')
            confidence = result.get('score', 0.0)
            abstained = result.get('abstained', False)
            
            # Map to exposure type and spectrograph
            exposure_type_ml, spectrograph_ml = self._map_model_class_to_exposure_type_and_spectrograph(predicted_class)
            
            return {
                'exposure_type_ml': exposure_type_ml,
                'exposure_type_ml_confidence': confidence,
                'exposure_type_ml_abstained': abstained,
                'spectrograph_ml': spectrograph_ml,
                'error': None,
            }
        except Exception as e:
            logger.error(f'Error classifying DataFile {datafile.pk} ({file_path}): {e}', exc_info=True)
            return {
                'exposure_type_ml': None,
                'exposure_type_ml_confidence': None,
                'exposure_type_ml_abstained': False,
                'spectrograph_ml': None,
                'error': str(e),
            }

    def classify_paths(self, paths: List[Path]) -> List[Dict]:
        """
        Batch classify multiple file paths.
        
        Parameters
        ----------
        paths : List[Path]
            List of file paths to classify
        
        Returns
        -------
        List[Dict]
            List of classification results (same format as classify_datafile)
        """
        results = []
        try:
            self._ensure_initialized()
        except Exception as e:
            # Return error for all files
            return [{
                'exposure_type_ml': None,
                'exposure_type_ml_confidence': None,
                'exposure_type_ml_abstained': False,
                'spectrograph_ml': None,
                'error': str(e),
            } for _ in paths]

        for path in paths:
            if not path.exists():
                results.append({
                    'exposure_type_ml': None,
                    'exposure_type_ml_confidence': None,
                    'exposure_type_ml_abstained': False,
                    'spectrograph_ml': None,
                    'error': f'File not found: {path}',
                })
                continue

            try:
                # Determine file type from extension
                ext = path.suffix.lower()
                file_type = 'FITS' if ext in ['.fits', '.fit', '.fts'] else 'TIFF' if ext in ['.tiff', '.tif'] else 'UNKNOWN'
                
                if not self.is_supported_format(file_type, path):
                    results.append({
                        'exposure_type_ml': None,
                        'exposure_type_ml_confidence': None,
                        'exposure_type_ml_abstained': False,
                        'spectrograph_ml': None,
                        'error': f'Unsupported file format: {file_type}',
                    })
                    continue

                # Call the classifier service - predict_paths expects a list
                path_str = str(path)
                batch_result = self._classifier.predict_paths([path_str], batch_size=1)
                
                # Extract classification result from batch results
                batch_results = batch_result.get('results', [])
                if not batch_results:
                    # Check for errors in defects
                    defects = batch_result.get('defects', [])
                    if defects:
                        error_msg = defects[0].get('message', 'Unknown error')
                        results.append({
                            'exposure_type_ml': None,
                            'exposure_type_ml_confidence': None,
                            'exposure_type_ml_abstained': False,
                            'spectrograph_ml': None,
                            'error': error_msg,
                        })
                    else:
                        results.append({
                            'exposure_type_ml': None,
                            'exposure_type_ml_confidence': None,
                            'exposure_type_ml_abstained': False,
                            'spectrograph_ml': None,
                            'error': 'No results returned from classifier',
                        })
                    continue
                
                # Get the first (and only) result
                result = batch_results[0]
                
                # Check for error in result
                if 'error' in result:
                    results.append({
                        'exposure_type_ml': None,
                        'exposure_type_ml_confidence': None,
                        'exposure_type_ml_abstained': False,
                        'spectrograph_ml': None,
                        'error': result['error'],
                    })
                    continue
                
                predicted_class = result.get('class', 'unknown')
                confidence = result.get('score', 0.0)
                abstained = result.get('abstained', False)
                
                # Map to exposure type and spectrograph
                exposure_type_ml, spectrograph_ml = self._map_model_class_to_exposure_type_and_spectrograph(predicted_class)
                
                results.append({
                    'exposure_type_ml': exposure_type_ml,
                    'exposure_type_ml_confidence': confidence,
                    'exposure_type_ml_abstained': abstained,
                    'spectrograph_ml': spectrograph_ml,
                    'error': None,
                })
            except Exception as e:
                logger.error(f'Error classifying file {path}: {e}', exc_info=True)
                results.append({
                    'exposure_type_ml': None,
                    'exposure_type_ml_confidence': None,
                    'exposure_type_ml_abstained': False,
                    'spectrograph_ml': None,
                    'error': str(e),
                })

        return results
