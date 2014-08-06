#!/usr/bin/env python

# Python Standard Modules
import os

# MUGQIC Modules
from core.config import *
from core.job import *

def mem(
    in1fastq,
    in2fastq=None,
    out_sam=None,
    read_group=None
    ):

    job = Job([in1fastq, in2fastq], [out_sam], [["bwa_mem", "module_bwa"]])

    job.command = ""
    if out_sam:
        job.command += "mkdir -p " + os.path.dirname(out_sam) + " && \\\n"

    idxbase = config.param('bwa_mem', 'genome_bwa_index', type='filepath')
    other_options = config.param('bwa_mem', 'other_options')

    job.command += \
"""bwa mem {other_options}{read_group} \\
  {idxbase} \\
  {in1fastq}{in2fastq}{out_sam}""".format(
        other_options=" \\\n  " + other_options if other_options else "",
        read_group=" \\\n  -R " + read_group if read_group else "",
        idxbase=idxbase,
        in1fastq=in1fastq,
        in2fastq=" \\\n  " + in2fastq if in2fastq else "",
        out_sam=" \\\n  > " + out_sam if out_sam else ""
    )

    return job