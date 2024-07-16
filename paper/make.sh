#!/bin/bash
cd paper

pdflatex -interaction=nonstopmode paper;
bibtex paper;
pdflatex -interaction=nonstopmode paper;
pdflatex -interaction=nonstopmode paper;

#mv paper.pdf paper/paper.pdf

rm paper.aux;
rm paper.bbl;
rm paper.blg;
#rm paper.log;
rm paper.out;
