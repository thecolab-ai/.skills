"""Parsers for Medsafe's public recalls database HTML tables."""
from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, parse_qs

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[]; self.tables=[]; self.table=None; self.table_depth=0
        self.row=None; self.cell=None; self.href=None
    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.table_depth == 0: self.table=[]
            self.table_depth += 1
        elif tag == "tr": self.row=[]
        elif tag in {"td","th"} and self.row is not None: self.cell=[]; self.href=None
        elif tag == "a" and self.cell is not None: self.href=dict(attrs).get("href")
        elif tag == "br" and self.cell is not None: self.cell.append(" ")
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in {"td","th"} and self.cell is not None:
            self.row.append({"text":" ".join("".join(self.cell).replace("\xa0"," ").split()),"href":self.href}); self.cell=None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            if self.table is not None: self.table.append(self.row)
            self.row=None
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1
            if self.table_depth == 0 and self.table is not None:
                self.tables.append(self.table); self.table=None

def parse_results(text, base, retrieved):
    p=Tables(); p.feed(text); out=[]
    expected = ["date", "brand name", "recall action"]
    result_tables=[]
    for table in p.tables:
        header_index=next((index for index,row in enumerate(table) if [cell["text"].casefold() for cell in row] == expected),None)
        if header_index is not None: result_tables.append((table,header_index))
    if not result_tables:
        if re.search(r'no (?:matching )?(?:recalls|results)', text, re.I): return []
        raise ValueError("Medsafe results page did not contain the expected results table")
    for table,header_index in result_tables:
        for row in table[header_index+1:]:
            if not row or not any(cell["text"] for cell in row): continue
            if len(row)!=3 or not row[1]["href"] or "RecallDetail.asp" not in row[1]["href"]:
                raise ValueError("Medsafe results table contained a malformed recall row")
            url=urljoin(base,row[1]["href"]); rid=parse_qs(urlparse(url).query).get("ID",[None])[0]
            # Medsafe legitimately publishes some rows with a blank Recall
            # Action cell, but date, brand and a detail ID identify a record.
            if not rid or not row[0]["text"] or not row[1]["text"]:
                raise ValueError("Medsafe results table contained a malformed recall row")
            out.append({"id":rid,"date_commenced":row[0]["text"],"brand":row[1]["text"],"recall_action":row[2]["text"],"source_url":url,"retrieved_at":retrieved})
    return out

def parse_detail(text, source, retrieved):
    p=Tables(); p.feed(text); fields={}
    for row in p.rows:
        if len(row)==2:
            key=re.sub(r"[^a-z0-9]+","_",row[0]["text"].lower()).strip("_")
            if key: fields[key]=row[1]["text"] or None
    if "medsafe_reference" not in fields: raise ValueError("Medsafe detail table missing reference")
    fields.update({"id":fields["medsafe_reference"],"source_url":source,"retrieved_at":retrieved})
    return fields
