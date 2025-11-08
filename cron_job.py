#!/usr/bin/env python3
"""
Cron job script to run feedback processing on schedule.
This script should be executed by Render Cron Jobs.
"""

import sys
import logging
from process_feedback import process_all_feedback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

if __name__ == "__main__":
    logging.info("=====================================")
    logging.info("Starting scheduled feedback processing")
    logging.info("=====================================")
    
    try:
        process_all_feedback()
        logging.info("Feedback processing completed successfully")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Fatal error in cron job: {e}")
        sys.exit(1)
