import os
from reportlab.pdfgen.canvas import Canvas
from PyPDF2 import PdfFileReader, PdfFileWriter
from pdfminer.pdfparser import PDFParser, PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTFigure
from pdfminer.converter import PDFPageAggregator
from difflib import SequenceMatcher
import logging
from cid import cid

BALLOT_DIR = "ballots"
RESULT_DIR = "results"
NAMES_CSV = "names.csv"
FILL_IMG = "oval.png"
FILL_SIZE = (13, 9)

# don't bother displaying pdfminer warnings (sooo many of them)
logging.getLogger("pdfminer").propagate = False
logging.getLogger().setLevel(logging.ERROR)

# checks if a string is a name
def check_valid(text, names):
    bestr = 0
    best = None
    for n in names:
        n = n.lower()
        for line in text:
            m = SequenceMatcher(None, line.lower(), n)
            if m.ratio() > bestr:
                bestr = m.ratio()
                best = True, n, bestr
    if bestr >= 0.9:
        return best
    else:
        return False, n, bestr

# bubbles in pdf at coordinates
def draw_bubbles(coords, sample, filled, page_size, bub_size):
    out_file = "TEMP_FILE.pdf"
    c = Canvas(out_file)
    c.setPageSize(page_size)
    for coord in coords:
        c.drawImage(filled, coord[0], coord[1] - 2, bub_size[0], -bub_size[1])

    c.showPage()
    c.save()
    output = PdfFileWriter()
    source = PdfFileReader(sample).getPage(0)
    bubbles = PdfFileReader(open(out_file, "rb")).getPage(0)

    source.mergePage(bubbles)
    output.addPage(source)
    return output

# extracts textboxes and textlines from pdf
def get_textboxes(layout):
    for lt_obj in layout:
        if isinstance(lt_obj, LTTextBox) or isinstance(lt_obj, LTTextLine):
            text = lt_obj.get_text().strip()
            names = text.split("\n")
            if text != "":
                yield (names, lt_obj.bbox)
            elif text != "":
                box_height = abs(lt_obj.bbox[3] - lt_obj.bbox[1]) / len(names)
                for i, t in enumerate(names):
                    box = lt_obj.bbox
                    box = (box[0], box[3] - (i * box_height * 1.05), box[2], box[3] - ((i + 1) * box_height))
                    yield (t, box)
        elif isinstance(lt_obj, LTFigure):
            get_textboxes(lt_obj)

# processes a ballot from start to finish
def process_sample(sample, names):
    parser = PDFParser(sample)
    doc = PDFDocument()
    parser.set_document(doc)
    doc.set_parser(parser)
    doc.initialize("")
    rsrcmgr = PDFResourceManager()
    laparams = LAParams()
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    page = doc.get_pages().__next__()
    interpreter.process_page(page)
    layout = device.get_result()

    correct_names = list()
    already_added = list()
    scores_added = list()
    for t in get_textboxes(layout):
        decoded_lines = list()
        for line in t[0]:
            for key in cid.keys():
                line = line.replace("(cid:" + str(key) + ")", cid[key])
            decoded_lines.append(line)
        t = (decoded_lines, t[1])

        valid, name, score = check_valid(t[0], names)
        if valid:
            added = False
            if name in already_added:
                index = already_added.index(name)
                if score > scores_added[index]:
                    correct_names[index] = t
                    scores_added[index] = score
                added = True
            if not added:
                correct_names.append(t)
                already_added.append(name)
                scores_added.append(score)


    coords = list()
    for textbox in correct_names:
        box = textbox[1]
        height = box[3] - box[1]
        corner = (box[2] + 2.6, box[3] - (height / 2) + 5.3)
        coords.append(corner)

    bubbled = draw_bubbles(coords, sample, FILL_IMG, (layout.width, layout.height), FILL_SIZE)
    return bubbled

# parses the csv containing names
def parse_csv(csv):
    valid = [x.strip() for x in csv.read().lower().replace(",", "").replace("\"", "").split("\n")]
    for i in range(valid.count("")):
        valid.remove("")
    return valid

if RESULT_DIR not in os.listdir():
    os.mkdir(RESULT_DIR)

csv = open(NAMES_CSV, 'r')
names = parse_csv(csv)

progress = 1
total = len(os.listdir(BALLOT_DIR))
for f in os.listdir(BALLOT_DIR):
    ext = f.split(".")[1]
    if ext == "pdf":
        print("(" + str(progress) + "/" + str(total) + ")" + " Processing " + f + "...")
        sample = open(BALLOT_DIR + "/" + f, 'rb')
        processed = process_sample(sample, names)
        out = open(RESULT_DIR + "/" + f, 'wb')
        processed.write(out)
        out.close()
        progress += 1

os.remove("TEMP_FILE.pdf")