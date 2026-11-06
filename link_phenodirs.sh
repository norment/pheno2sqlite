#!/bin/bash
# link different phenotype sources to local "raw" directory

PHENODIR=/ess/p697/data/durable/phenotypes
RAWDIR=raw
mkdir -p $RAWDIR
ln -s $PHENODIR/kpr/2026-10-19 raw/kpr/2026-10-19
ln -s $PHENODIR/kuhr/2023-10-23/ raw/kuhr/2023-10-23
# ln -s $PHENODIR/lmr/20XX raw/lmr
ln -s $PHENODIR/mbrn/2025-12-16/ raw/mbrn/2025-12-16
ln -s $PHENODIR/mobaQ raw/mobaQ
ln -s $PHENODIR/npr/2026-10-19 raw/npr/2026-10-19
# ln -s $PHENODIR/ssb/20XX raw/ssb/20XX

