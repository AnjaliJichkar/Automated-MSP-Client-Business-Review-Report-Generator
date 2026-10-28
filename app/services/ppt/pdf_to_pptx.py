"""
PDF to PPTX Converter using ConvertHub API
Converts PDF files to PowerPoint presentations
"""

from dotenv import load_dotenv
import requests
import time
import os
import logging
from pptx import Presentation
from pptx.dml.color import RGBColor

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

API_BASE = "https://api.converthub.com/v2"


def add_white_background(pptx_file: str) -> bool:
    """
    Add white background to all slides in the PPTX to avoid grey borders

    Args:
        pptx_file: Path to PPTX file

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info("Adding white background to slides...")
        prs = Presentation(pptx_file)

        for slide in prs.slides:
            # Set slide background to white
            background = slide.background
            fill = background.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor(255, 255, 255)  # White

        # Save the modified presentation
        prs.save(pptx_file)
        logger.info("White background applied to all slides")
        return True
    except Exception as e:
        logger.warning(f"Could not add white background: {e}")
        logger.warning("PPTX still saved, but may have grey borders")
        return False


def convert_pdf_to_pptx(input_pdf: str, output_pptx: str) -> bool:
    """
    Convert PDF to PPTX using ConvertHub API

    Args:
        input_pdf: Path to input PDF file
        output_pptx: Path where PPTX should be saved

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load API key from environment
        api_key = os.getenv('CONVERTHUB_API_KEY')
        if not api_key:
            logger.error("CONVERTHUB_API_KEY not found in environment variables")
            return False

        # Step 1 — Submit file for conversion
        logger.info(f"Submitting PDF to ConvertHub: {os.path.basename(input_pdf)}")

        with open(input_pdf, "rb") as f:
            files = {"file": (os.path.basename(input_pdf), f)}
            data = {"target_format": "pptx"}
            headers = {"Authorization": f"Bearer {api_key}"}

            response = requests.post(
                f"{API_BASE}/convert",
                headers=headers,
                files=files,
                data=data
            )

        # Parse job info
        resp_json = response.json()
        job_id = resp_json.get("job_id") or resp_json.get("data", {}).get("job_id")

        if not job_id:
            logger.error(f"Failed to start conversion: {resp_json}")
            return False

        logger.info(f"ConvertHub job created: {job_id}")

        # Step 2 — Poll job status until done
        headers = {"Authorization": f"Bearer {api_key}"}
        status = None
        download_url = None
        max_attempts = 30  # 60 seconds max (2s * 30)
        attempts = 0

        while attempts < max_attempts:
            time.sleep(2)
            attempts += 1

            status_resp = requests.get(f"{API_BASE}/jobs/{job_id}", headers=headers)
            status_json = status_resp.json()

            # status normally under "status" or "data.status"
            status = status_json.get("status") or status_json.get("data", {}).get("status")
            logger.info(f"ConvertHub status: {status} (attempt {attempts}/{max_attempts})")

            if status == "completed":
                # Extract download URL
                download_url = \
                    status_json.get("result", {}).get("download_url") or \
                    status_json.get("data", {}).get("result", {}).get("download_url")
                break
            elif status == "failed":
                logger.error(f"Conversion failed: {status_json}")
                return False
            # still processing → loop

        if not download_url:
            logger.error("No download URL found after polling")
            return False

        # Step 3 — Download result
        logger.info("Downloading converted PPTX...")
        dl_resp = requests.get(download_url)

        with open(output_pptx, "wb") as out:
            out.write(dl_resp.content)

        logger.info(f"PPTX saved: {output_pptx} ({len(dl_resp.content)} bytes)")

        # Step 4 — Add white background to remove grey borders
        add_white_background(output_pptx)

        return True

    except Exception as e:
        logger.error(f"Error converting PDF to PPTX: {e}")
        return False
