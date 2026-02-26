import subprocess
import re
from city_scrapers.spiders.sandie_planeboards import spider_configs

def run_spiders():
    for config in spider_configs:
        spider_name = config["name"]
        output_file = f"{spider_name}.json"

        cmd = [
            "scrapy",
            "crawl",
            spider_name,
            "-O",
            output_file,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False  # Don't raise exception on non-zero exit
        )

        print(result.stdout)
        if result.stderr:
            print(result.stderr)

        combined_output = result.stdout + result.stderr
        if re.search(r"'log_count/ERROR':\s*[1-9]\d*", combined_output):
            print(f"{spider_name}. Stopping execution.")
            break

if __name__ == "__main__":
    run_spiders()