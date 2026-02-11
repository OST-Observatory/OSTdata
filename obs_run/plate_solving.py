"""
Plate Solving Framework

Provides a flexible framework for plate solving with support for multiple tools.
Currently supports Watney, with extensibility for additional solvers.
"""

from __future__ import annotations

import json
import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, List

from django.conf import settings

logger = logging.getLogger(__name__)


class PlateSolver(ABC):
    """Abstract base class for plate solving tools."""

    @abstractmethod
    def solve(self, image_path: str, min_radius: float, max_radius: float) -> Dict:
        """
        Attempt to solve an image.

        Args:
            image_path: Path to the image file
            min_radius: Minimum field radius in degrees
            max_radius: Maximum field radius in degrees

        Returns:
            Dictionary with solution data (must include 'success': True)

        Raises:
            Exception: If solving fails
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the solver tool is installed and available."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return the identifier name of this solver."""
        pass


class WatneySolver(PlateSolver):
    """Watney plate solver implementation."""

    def __init__(self, executable_path: Optional[str] = None):
        """
        Initialize Watney solver.

        Args:
            executable_path: Path to watney-solve executable. If None, uses default from settings.
        """
        self.executable_path = executable_path or getattr(
            settings, 'WATNEY_SOLVE_PATH', 'watney-solve'
        )
        self.timeout = getattr(settings, 'PLATE_SOLVING_TIMEOUT_SECONDS', 300)

    def get_name(self) -> str:
        return 'watney'

    def is_available(self) -> bool:
        """Check if watney-solve is available."""
        try:
            result = subprocess.run(
                [self.executable_path, '--version'],
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return False

    def solve(self, image_path: str, min_radius: float, max_radius: float) -> Dict:
        """
        Solve an image using Watney.

        Args:
            image_path: Path to the image file
            min_radius: Minimum field radius in degrees (must be > 0.1)
            max_radius: Maximum field radius in degrees (must be <= 30)

        Returns:
            Dictionary with solution data

        Raises:
            Exception: If solving fails
        """
        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        # Ensure radius constraints
        min_radius = max(0.1, min_radius)
        max_radius = min(30.0, max_radius)

        if min_radius >= max_radius:
            raise ValueError(f"min_radius ({min_radius}) must be < max_radius ({max_radius})")

        cmd = [
            self.executable_path,
            'solve',
            'blind',
            '--image', str(image_path),
            '--min-radius', str(min_radius),
            '--max-radius', str(max_radius),
            '--extended',
            '--out-format', 'json'
        ]

        try:
            logger.debug(f"Running Watney: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.timeout,
                text=True,
                check=False  # Don't raise on non-zero exit
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise RuntimeError(f"Watney failed with exit code {result.returncode}: {error_msg}")

            # Parse JSON output
            try:
                output = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse Watney JSON output: {e}\nOutput: {result.stdout}")

            if not output.get('success', False):
                raise RuntimeError("Watney returned success=false")

            return output

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Watney solver timed out after {self.timeout} seconds")
        except FileNotFoundError:
            raise FileNotFoundError(f"Watney executable not found: {self.executable_path}")
        except Exception as e:
            if isinstance(e, (TimeoutError, FileNotFoundError, ValueError, RuntimeError)):
                raise
            raise RuntimeError(f"Unexpected error running Watney: {e}")


class PlateSolvingService:
    """Service that coordinates multiple plate solvers with fallback support."""

    def __init__(self, solvers: Optional[List[PlateSolver]] = None):
        """
        Initialize the plate solving service.

        Args:
            solvers: List of solver instances to try in order. If None, creates from settings.
        """
        if solvers is None:
            solvers = self._create_solvers_from_settings()
        self.solvers = solvers

    def _create_solvers_from_settings(self) -> List[PlateSolver]:
        """Create solver instances from Django settings."""
        solver_list = []
        tool_names = getattr(settings, 'PLATE_SOLVING_TOOLS', ['watney'])

        for tool_name in tool_names:
            if tool_name == 'watney':
                solver = WatneySolver()
                if solver.is_available():
                    solver_list.append(solver)
                else:
                    logger.warning(f"Watney solver configured but not available")
            else:
                logger.warning(f"Unknown plate solving tool: {tool_name}")

        return solver_list

    def solve(self, image_path: str, min_radius: float, max_radius: float) -> Optional[Dict]:
        """
        Attempt to solve an image using configured solvers in order.

        Args:
            image_path: Path to the image file
            min_radius: Minimum field radius in degrees
            max_radius: Maximum field radius in degrees

        Returns:
            Solution dictionary if successful, None if all solvers failed
        """
        if not self.solvers:
            logger.error("No plate solving tools available")
            return None

        for solver in self.solvers:
            try:
                logger.info(f"Attempting plate solve with {solver.get_name()} for {image_path}")
                result = solver.solve(image_path, min_radius, max_radius)
                logger.info(f"Plate solve successful with {solver.get_name()}")
                # Add tool name to result
                result['tool'] = solver.get_name()
                return result
            except Exception as e:
                logger.warning(f"Plate solve failed with {solver.get_name()}: {e}")
                continue

        logger.error(f"All plate solvers failed for {image_path}")
        return None

    def calculate_radius_from_fov(self, fov_x: float, fov_y: float) -> tuple[float, float]:
        """
        Calculate min/max radius from field of view.

        Args:
            fov_x: Field of view width in degrees
            fov_y: Field of view height in degrees

        Returns:
            Tuple of (min_radius, max_radius) in degrees
        """
        margin = getattr(settings, 'PLATE_SOLVING_FOV_MARGIN', 0.2)
        min_radius_default = getattr(settings, 'PLATE_SOLVING_MIN_RADIUS', 0.1)
        max_radius_default = getattr(settings, 'PLATE_SOLVING_MAX_RADIUS', 30.0)

        if fov_x > 0 and fov_y > 0:
            max_fov = max(fov_x, fov_y)  # degrees
            margin_amount = max_fov * margin
            min_radius = max(min_radius_default, max_fov * 0.5 - margin_amount)
            max_radius = min(max_radius_default, max_fov * 1.5 + margin_amount)
        else:
            # Fallback to defaults
            min_radius = min_radius_default
            max_radius = max_radius_default

        return min_radius, max_radius


def solve_and_update_datafile(datafile, service=None, save=True):
    """
    Attempt to plate solve a DataFile and update it with the solution.
    
    This is a helper function that encapsulates the common logic for:
    - Calculating radius from FOV
    - Attempting plate solving
    - Extracting and setting WCS fields from the solution
    - Handling errors
    
    Args:
        datafile: DataFile instance to solve
        service: Optional PlateSolvingService instance (creates new if None)
        save: Whether to save the DataFile after updating (default: True)
    
    Returns:
        dict with keys:
            - 'success': bool - Whether plate solving succeeded
            - 'error': str or None - Error message if failed
            - 'tool': str or None - Tool name if succeeded
    """
    from pathlib import Path
    from django.utils import timezone
    import logging
    
    logger = logging.getLogger(__name__)
    
    if service is None:
        service = PlateSolvingService()
    
    try:
        image_path = Path(datafile.datafile)
        if not image_path.exists():
            error_msg = f"File not found: {image_path}"
            if save:
                datafile.plate_solve_attempted_at = timezone.now()
                datafile.plate_solve_error = error_msg
                datafile.save(update_fields=['plate_solve_attempted_at', 'plate_solve_error'])
            return {'success': False, 'error': error_msg, 'tool': None}
        
        # Calculate radius from FOV
        min_radius, max_radius = service.calculate_radius_from_fov(
            datafile.fov_x if datafile.fov_x > 0 else -1,
            datafile.fov_y if datafile.fov_y > 0 else -1
        )
        
        # Attempt plate solving
        solution = service.solve(str(image_path), min_radius, max_radius)
        
        if solution and solution.get('success'):
            # Update DataFile with solution
            datafile.plate_solved = True
            datafile.plate_solve_attempted_at = timezone.now()
            datafile.plate_solve_error = None
            datafile.plate_solve_tool = solution.get('tool', 'unknown')
            
            # Extract WCS fields from solution
            datafile.wcs_ra = solution.get('ra')
            datafile.wcs_dec = solution.get('dec')
            datafile.wcs_ra_hms = solution.get('ra_hms')
            datafile.wcs_dec_dms = solution.get('dec_dms')
            datafile.wcs_field_radius = solution.get('fieldRadius')
            datafile.wcs_orientation = solution.get('orientation')
            datafile.wcs_pix_scale = solution.get('pixScale')
            datafile.wcs_parity = solution.get('parity')
            datafile.wcs_field_width = solution.get('fieldWidth') or solution.get('field_width')
            datafile.wcs_field_height = solution.get('fieldHeight') or solution.get('field_height')
            
            # FITS WCS parameters
            datafile.wcs_cd1_1 = solution.get('fits_cd1_1')
            datafile.wcs_cd1_2 = solution.get('fits_cd1_2')
            datafile.wcs_cd2_1 = solution.get('fits_cd2_1')
            datafile.wcs_cd2_2 = solution.get('fits_cd2_2')
            datafile.wcs_cdelt1 = solution.get('fits_cdelt1')
            datafile.wcs_cdelt2 = solution.get('fits_cdelt2')
            datafile.wcs_crota1 = solution.get('fits_crota1')
            datafile.wcs_crota2 = solution.get('fits_crota2')
            datafile.wcs_crpix1 = solution.get('fits_crpix1')
            datafile.wcs_crpix2 = solution.get('fits_crpix2')
            datafile.wcs_crval1 = solution.get('fits_crval1')
            datafile.wcs_crval2 = solution.get('fits_crval2')
            
            if save:
                datafile.save()
            
            return {
                'success': True,
                'error': None,
                'tool': datafile.plate_solve_tool
            }
        else:
            error_msg = "Plate solving returned success=false"
            if save:
                datafile.plate_solve_attempted_at = timezone.now()
                datafile.plate_solve_error = error_msg
                datafile.save(update_fields=['plate_solve_attempted_at', 'plate_solve_error'])
            return {'success': False, 'error': error_msg, 'tool': None}
            
    except Exception as e:
        logger.exception(f"Error plate solving file {datafile.pk}: {e}")
        error_msg = str(e)[:500]  # Limit error length
        if save:
            datafile.plate_solve_attempted_at = timezone.now()
            datafile.plate_solve_error = error_msg
            datafile.save(update_fields=['plate_solve_attempted_at', 'plate_solve_error'])
        return {'success': False, 'error': error_msg, 'tool': None}
