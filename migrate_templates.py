import os
import re


def migrate_templates(directory):
    # Regex to find url_for('static', filename='...') or url_for("static", filename="...")
    # It also handles potential spaces and different quotes.
    pattern = re.compile(r"url_for\s*\(\s*['\"]static['\"]\s*,\s*filename\s*=")

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()

                if pattern.search(content):
                    new_content = content.replace("filename=", "path=")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"Updated: {path}")


if __name__ == "__main__":
    migrate_templates("templates")
