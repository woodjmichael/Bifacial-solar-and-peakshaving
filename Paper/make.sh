#!/bin/bash
cp paper.tex ./tex/paper.tex;
cp mendeley.bib ./tex/mendeley.bib;
cd tex;
pdflatex -interaction=nonstopmode paper;
bibtex paper;
pdflatex -interaction=nonstopmode paper;
pdflatex -interaction=nonstopmode paper;
mv paper.pdf ../paper.pdf;