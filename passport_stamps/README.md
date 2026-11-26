# Passport stamp extraction

This local Python utility finds likely colored stamp regions on scanned passport
pages, OCRs each crop, and saves each stamp as a separate JPG named with any
recognized text. OCR runs locally; page images are not uploaded.

Install the Python dependencies and the Tesseract OCR executable:

```sh
python -m pip install -r passport_stamps/requirements.txt
```

Install Tesseract separately for your operating system. On Windows, if it is
not on `PATH`, provide its executable path with `--tesseract-cmd`.
The default OCR language is English; use `--lang eng+fra` (for example) when
additional Tesseract language data is installed.

Process one image or all supported images in a directory:

```sh
python passport_stamps/extract_stamps.py "C:\scans\passport-page.jpg"
python passport_stamps/extract_stamps.py "C:\scans\passport-pages" --output "C:\scans\stamps"
```

The default output directory is `passport_stamps` beside the input image or
inside the input directory. Crop margins default to 4%; change this with
`--padding 0.06`. Automatic detection targets colored ink, so it may miss
black-only stamps or include unrelated colored page details. Use `--manual` to
select rectangles yourself when the automatic boundaries are not suitable.

Example with manual selection and an explicit Tesseract path:

```sh
python passport_stamps/extract_stamps.py "C:\scans\passport-page.jpg" --manual --tesseract-cmd "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

If OCR finds no readable text, the saved filename contains the page name and
stamp number only. Existing files are never overwritten.
