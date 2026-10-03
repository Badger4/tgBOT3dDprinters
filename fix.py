import re

with open('services/hms_resolver.py', 'r', encoding='utf-8') as f:
    content = f.read()

repl = '''# --- Category 0700: Micro Lidar & Optical Calibration ---
    "HMS_0700_8001": "Закінчився філамент в AMS (Слот 1)",
    "HMS_0700_8002": "Закінчився філамент в AMS (Слот 2)",
    "HMS_0700_8003": "Закінчився філамент в AMS (Слот 3)",
    "HMS_0700_8004": "Закінчився філамент в AMS (Слот 4)",
    "HMS_0700_8011": "Закінчився філамент в AMS",
    "HMS_0700_2000": "Закінчився філамент (зовнішня котушка)",
    "HMS_07FF_2000": "Закінчився філамент (зовнішня котушка)",
    "HMS_07FE_2000": "Закінчився філамент (зовнішня котушка)",
    "HMS_0300_0D00_0001_0003": "Закінчився філамент (екструдер порожній)",
'''

content = re.sub(r'# --- Category 0700: Micro Lidar.*?(?=    "HMS_0700_0100_0001_0001")', repl, content, flags=re.DOTALL)

with open('services/hms_resolver.py', 'w', encoding='utf-8') as f:
    f.write(content)
