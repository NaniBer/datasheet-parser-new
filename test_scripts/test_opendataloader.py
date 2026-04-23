import opendataloader_pdf
import json
import os

# Test on 74HC595 datasheet
print("Testing OpenDataLoader on 74HC595_TI.pdf...")

opendataloader_pdf.convert(
    input_path=["pdfs/74HC595_TI.pdf"],
    output_dir="output/",
    format="json"
)

# Read the output
output_file = "output/74HC595_TI.json"
if not os.path.exists(output_file):
    print(f"Error: {output_file} not found!")
    exit(1)

with open(output_file, "r") as f:
    data = json.load(f)

# Print structure
print(f"\n{'='*60}")
print(f"Total elements: {len(data)}")
print(f"Element types: {sorted(set(item['type'] for item in data))}")
print(f"{'='*60}\n")

# Find tables
tables = [item for item in data if item['type'] == 'table']
print(f"Number of tables: {len(tables)}")

# Analyze each table
for i, table in enumerate(tables, 1):
    print(f"\n{'='*60}")
    print(f"Table {i}:")
    print(f"  Page: {table.get('page number', 'N/A')}")
    print(f"  Bounding box: {table.get('bounding box', 'N/A')}")

    if 'content' in table:
        content = table['content']
        print(f"  Content type: {type(content)}")

        if isinstance(content, list):
            print(f"  Number of rows: {len(content)}")
            if content:
                print(f"  First row columns: {len(content[0]) if isinstance(content[0], list) else 'N/A'}")

                # Show first few rows
                print(f"\n  First 5 rows:")
                for j, row in enumerate(content[:5], 1):
                    print(f"    Row {j}: {row}")
        else:
            print(f"  Content: {content[:200] if len(str(content)) > 200 else content}...")

    print(f"{'='*60}\n")

# Find pages with tables
pages_with_tables = sorted(set(table.get('page number', 0) for table in tables if 'page number' in table))
print(f"Pages with tables: {pages_with_tables}")

# Save detailed analysis for the first table
if tables:
    with open("output/opendataloader_analysis.txt", "w") as f:
        f.write(f"OpenDataLoader Analysis for 74HC595_TI.pdf\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"Total elements: {len(data)}\n")
        f.write(f"Element types: {sorted(set(item['type'] for item in data))}\n")
        f.write(f"Number of tables: {len(tables)}\n")
        f.write(f"Pages with tables: {pages_with_tables}\n\n")

        f.write(f"First table (full structure):\n")
        f.write(json.dumps(tables[0], indent=2, default=str))

    print(f"\nDetailed analysis saved to: output/opendataloader_analysis.txt")
