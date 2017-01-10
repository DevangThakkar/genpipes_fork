#!/usr/bin/env python

################################################################################
# Copyright (C) 2014, 2015 GenAP, McGill University and Genome Quebec Innovation Centre
#
# This file is part of MUGQIC Pipelines.
#
# MUGQIC Pipelines is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# MUGQIC Pipelines is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with MUGQIC Pipelines.  If not, see <http://www.gnu.org/licenses/>.
################################################################################

# Python Standard Modules
import logging
import math
import os
import re
import sys

# Append mugqic_pipelines directory to Python library path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))))

# MUGQIC Modules
from core.config import *
from core.job import *
from core.pipeline import *
from bfx.readset import *

from bfx import bismark
from bfx import picard2 as picard
from bfx import bedtools
from bfx import samtools
from bfx import gatk
from bfx import igvtools

from pipelines.dnaseq import dnaseq

log = logging.getLogger(__name__)

class MethylSeq(dnaseq.DnaSeq):
    """
    Methyl-Seq Pipeline
    ================

    The standard MUGQIC Methyle-Seq pipeline uses Bismark to align reads to the reference genome. Treatment
    and filtering of mapped reads approaches as mark duplicate reads, recalibration
    and sort are executed using Picard and GATK. Samtools MPILEUP and bcftools are used to produce
    the standard SNP and indels variants file (VCF). Additional SVN annotations mostly applicable
    to human samples include mappability flags, dbSNP annotation and extra information about SVN
    by using published databases.  The SNPeff tool is used to annotate variants using an integrated database
    of functional predictions from multiple algorithms (SIFT, Polyphen2, LRT and MutationTaster, PhyloP and GERP++, etc.)
    and to calculate the effects they produce on known genes. A list of effects and annotations
    that SnpEff calculate can be found [here](http://snpeff.sourceforge.net/faq.html#What_effects_are_predicted?).

    A summary html report is automatically generated by the pipeline. This report contains description
    of the sequencing experiment as well as a detailed presentation of the pipeline steps and results.
    Various Quality Control (QC) summary statistics are included in the report and additional QC analysis
    is accessible for download directly through the report. The report includes also the main references
    of the software and methods used during the analysis, together with the full list of parameters
    that have been passed to the pipeline main script.
    """

    def bismark_align(self):
        """
        """

        jobs = []
        for readset in self.readsets:
            trim_file_prefix = os.path.join("trim", readset.sample.name, readset.name + ".trim.")
            alignment_directory = os.path.join("alignment", readset.sample.name)
            readset_bam = os.path.join(alignment_directory, readset.name, readset.name + ".sorted.bam")

            # Find input readset FASTQs first from previous trimmomatic job, then from original FASTQs in the readset sheet
            if readset.run_type == "PAIRED_END":
                candidate_input_files = [[trim_file_prefix + "pair1.fastq.gz", trim_file_prefix + "pair2.fastq.gz"]]
                if readset.fastq1 and readset.fastq2:
                    candidate_input_files.append([readset.fastq1, readset.fastq2])
                if readset.bam:
                    candidate_input_files.append([re.sub("\.bam$", ".pair1.fastq.gz", readset.bam), re.sub("\.bam$", ".pair2.fastq.gz", readset.bam)])
                [fastq1, fastq2] = self.select_input_files(candidate_input_files)
            elif readset.run_type == "SINGLE_END":
                candidate_input_files = [[trim_file_prefix + "single.fastq.gz"]]
                if readset.fastq1:
                    candidate_input_files.append([readset.fastq1])
                if readset.bam:
                    candidate_input_files.append([re.sub("\.bam$", ".single.fastq.gz", readset.bam)])
                [fastq1] = self.select_input_files(candidate_input_files)
                fastq2 = None
            else:
                raise Exception("Error: run type \"" + readset.run_type +
                "\" is invalid for readset \"" + readset.name + "\" (should be PAIRED_END or SINGLE_END)!")

            jobs.append(
                concat_jobs([
                    Job(command="mkdir -p " + os.path.dirname(readset_bam)),
                    bismark.align(
                        fastq1,
                        fastq2,
                        os.path.dirname(readset_bam),
                        re.sub(".bam", "_noRG.bam", readset_bam)
                    ),
                    Job(command="rename " + re.sub(".sorted.bam", "*bismark*.bam", readset_bam) + " " + re.sub(".bam", "_noRG.bam", readset_bam) + " " + os.path.join(os.path.dirname(readset_bam), "*.bam")),
                    Job(command="rename " + re.sub(".sorted.bam", "*bismark*_report.txt", readset_bam) + " " + re.sub(".bam", "_noRG_report.txt", readset_bam) + " " + os.path.join(os.path.dirname(readset_bam), "*_report.txt"))
                ], name="bismark_align." + readset.name)
            )

        return jobs

    def picard_add_read_groups(self):
        """
        """

        jobs = []
        for readset in self.readsets:
            alignment_directory = os.path.join("alignment", readset.sample.name)

            candidate_input_files = [[os.path.join(alignment_directory, readset.name, readset.name + ".sorted_noRG.bam")]]
            if readset.bam:
                candidate_input_files.append([readset.bam])
            [input_bam] = self.select_input_files(candidate_input_files)
            output_bam = re.sub("_noRG.bam", ".bam", input_bam)

            jobs.append(
                concat_jobs([
                    Job(command="mkdir -p " + alignment_directory),
                    picard.add_or_replace_read_groups(
                        input_bam,
                        output_bam,
                        readset.name,
                        readset.library,
                        readset.lane,
                        readset.sample.name
                    )
                ], name="picard_add_read_groups." + readset.name)
            )

        return jobs

    def metrics(self):
        """
        Compute metrics and generate coverage tracks per sample. Multiple metrics are computed at this stage:
        Number of raw reads, Number of filtered reads, Number of aligned reads, Number of duplicate reads,
        Median, mean and standard deviation of insert sizes of reads after alignment, percentage of bases
        covered at X reads (%_bases_above_50 means the % of exons bases which have at least 50 reads)
        whole genome or targeted percentage of bases covered at X reads (%_bases_above_50 means the % of exons
        bases which have at least 50 reads). A TDF (.tdf) coverage track is also generated at this step
        for easy visualization of coverage in the IGV browser.
        """

        ##check the library status
        library, bam = {}, {}
        for readset in self.readsets:
            if not library.has_key(readset.sample) :
                library[readset.sample]="SINGLE_END"
            if readset.run_type == "PAIRED_END" :
                library[readset.sample]="PAIRED_END"
            if not bam.has_key(readset.sample):
                bam[readset.sample]=""
            if readset.bam:
                bam[readset.sample]=readset.bam

        jobs = []
        for sample in self.samples:
            file_prefix = os.path.join("alignment", sample.name, sample.name + ".sorted.")

            candidate_input_files = [[file_prefix + "bam"]]
            if bam[sample]:
                candidate_input_files.append([bam[sample]])
            [input] = self.select_input_files(candidate_input_files)

            job = picard.collect_multiple_metrics(input, file_prefix + "all.metrics",  library_type=library[sample])
            job.name = "picard_collect_multiple_metrics." + sample.name
            jobs.append(job)

            # Compute genome coverage with GATK
            job = gatk.depth_of_coverage(input, file_prefix + "all.coverage", bvatools.resolve_readset_coverage_bed(sample.readsets[0]))
            job.name = "gatk_depth_of_coverage.genome." + sample.name
            jobs.append(job)

            # Compute genome or target coverage with BVATools
            job = bvatools.depth_of_coverage(
                input,
                file_prefix + "coverage.tsv",
                bvatools.resolve_readset_coverage_bed(sample.readsets[0]),
                other_options=config.param('bvatools_depth_of_coverage', 'other_options', required=False)
            )

            job.name = "bvatools_depth_of_coverage." + sample.name
            jobs.append(job)

            job = igvtools.compute_tdf(input, input + ".tdf")
            job.name = "igvtools_compute_tdf." + sample.name
            jobs.append(job)

        return jobs

    def bismark_dedup(self):
        """
        """

        # Check the library status
        library = {}
        for readset in self.readsets:
            if not library.has_key(readset.sample) :
                library[readset.sample]="SINGLE_END"
            if readset.run_type == "PAIRED_END" :
                library[readset.sample]="PAIRED_END"

        jobs = []
        for sample in self.samples:
            alignment_directory = os.path.join("alignment", sample.name)
            bam_input = os.path.join(alignment_directory, sample.name + ".sorted.bam")
            bam_readset_sorted = re.sub(".sorted.bam", ".readset_sorted.bam", bam_input)
            dedup_bam_readset_sorted = re.sub(".bam", ".dedup.bam", bam_readset_sorted)
            bam_output = re.sub("readset_", "", dedup_bam_readset_sorted)

            job = concat_jobs([
                Job(command="mkdir -p " + alignment_directory),
                picard.sort_sam(
                    bam_input,
                    bam_readset_sorted,
                    "queryname"
                ),
                bismark.dedup(
                    bam_readset_sorted,
                    dedup_bam_readset_sorted,
                    library[sample]
                ),
                Job(command="mv " + re.sub(".bam", ".deduplicated.bam", bam_readset_sorted) + " " + dedup_bam_readset_sorted),
                picard.sort_sam(
                    dedup_bam_readset_sorted,
                    bam_output
                )
            ])
            job.name = "bismark_dedup." + sample.name

            jobs.append(job)

        return jobs

    def wiggle_tracks(self):
        """
        Generate wiggle tracks suitable for multiple browsers.
        """

        jobs = []

        ##check the library status
        library = {}
        for readset in self.readsets:
            if not library.has_key(readset.sample) :
                library[readset.sample]="PAIRED_END"
            if readset.run_type == "SINGLE_END" :
                library[readset.sample]="SINGLE_END"

        for sample in self.samples:
            alignment_directory = os.path.join("alignment", sample.name)

            candidate_input_files = [[os.path.join(alignment_directory, sample.name + ".readset_sorted.dedup.bam")]]
            candidate_input_files.append([os.path.join(alignment_directory, sample.name + ".sorted.dedup.bam")])

            [input_bam] = self.select_input_files(candidate_input_files)

            bed_graph_prefix = os.path.join("tracks", sample.name, sample.name)
            big_wig_prefix = os.path.join("tracks", "bigWig", sample.name)

            bed_graph_output = bed_graph_prefix + ".bedGraph"
            big_wig_output = big_wig_prefix + ".bw"

            if input_bam == os.path.join(alignment_directory, sample.name + ".readset_sorted.dedup.bam") :
                jobs.append(
                    concat_jobs([
                        Job(command="mkdir -p " + os.path.join("tracks", sample.name) + " " + os.path.join("tracks", "bigWig"), removable_files=["tracks"]),
                        picard.sort_sam(
                            input_bam,
                            re.sub("readset_sorted", "sorted", input_bam),
                            "coordinate"
                        ),
                        bedtools.graph(re.sub("readset_sorted", "sorted", input_bam), bed_graph_output, big_wig_output, library[sample])
                    ], name="wiggle." + re.sub(".bedGraph", "", os.path.basename(bed_graph_output)))
                )
            else :
                jobs.append(
                    concat_jobs([
                        Job(command="mkdir -p " + os.path.join("tracks", sample.name) + " " + os.path.join("tracks", "bigWig"), removable_files=["tracks"]),
                        bedtools.graph(input_bam, bed_graph_output, big_wig_output, library[sample])
                    ], name="wiggle." + re.sub(".bedGraph", "", os.path.basename(bed_graph_output)))
                )

        return jobs


    def puc19_lambda_reads(self):
        """
        """

        jobs = []
        for sample in self.samples:
            alignment_directory = os.path.join("alignment", sample.name)

            candidate_input_files = [[os.path.join(alignment_directory, sample.name + ".sorted.dedup.bam")]]
            candidate_input_files.append([os.path.join(alignment_directory, sample.name + ".sorted.bam")])
            [input_file] = self.select_input_files(candidate_input_files)

            puc19_out_file = re.sub(".bam", ".pUC19_reads.txt", input_file)
            puc19_job = Job(
                [input_file],
                [puc19_out_file],
                [
                    ['puc19_lambda_reads', 'module_samtools']
                ],
                command="samtools view " + input_file + " | grep pUC19 > " + puc19_out_file,
                name="pUC19." + sample.name
            )

            lambda_out_file = re.sub(".bam", ".lambda_reads.txt", input_file)
            lambda_job = Job(
                [input_file],
                [lambda_out_file],
                [
                    ['puc19_lambda_reads', 'module_samtools']
                ],
                command="samtools view " + input_file + " | grep lambda > " + lambda_out_file,
                name="lambda." + sample.name
            )
            jobs.append(
                concat_jobs([
                    Job(command="mkdir -p " + alignment_directory),
                    puc19_job,
                    lambda_job
                ], name="puc19_lambda_reads." + sample.name)
            )

        return jobs

    def methylation_call(self):
        """
        """

        # Check the library status
        library = {}
        for readset in self.readsets:
            if not library.has_key(readset.sample) :
                library[readset.sample]="SINGLE_END"
            if readset.run_type == "PAIRED_END" :
                library[readset.sample]="PAIRED_END"

        jobs = []
        for sample in self.samples:
            alignment_directory = os.path.join("alignment", sample.name)

            candidate_input_files = [[os.path.join(alignment_directory, sample.name + ".readset_sorted.dedup.bam")]]
            candidate_input_files.append([os.path.join(alignment_directory, sample.name + ".sorted.dedup.bam")])
            candidate_input_files.append([os.path.join(alignment_directory, sample.name + ".sorted.bam")])
            [input_file] = self.select_input_files(candidate_input_files)

            methyl_directory = os.path.join("methylation_call", sample.name)
            output_files = [
                os.path.join( methyl_directory, re.sub( ".bam", ".bedGraph.gz", os.path.basename(input_file) ) ),
                os.path.join( methyl_directory, re.sub( ".bam", ".bismark.cov.gz", os.path.basename(input_file) ) )
            ]

            if input_file == os.path.join(alignment_directory, sample.name + ".readset_sorted.dedup.bam") :
                bismark_job = bismark.methyl_call(
                    input_file,
                    output_files,
                    library[sample]
                )
            else :
                bismark_job = concat_jobs([
                    picard.sort_sam(
                        input_file,
                        re.sub("sorted", "readset_sorted", input_file),
                        "queryname"
                    ),
                    bismark.methyl_call(
                        re.sub("sorted", "readset_sorted", input_file),
                        output_files,
                        library[sample]
                    )
                ])

            jobs.append(
                concat_jobs([
                    Job(command="mkdir -p " + methyl_directory),
                    bismark_job,
                ], name="bismark_methyl_call." + sample.name)
            )

        return jobs

    def bed_graph(self):
        """
        """

        jobs = []
        for sample in self.samples:
            methyl_directory = os.path.join("methylation_call", sample.name)

            candidate_input_files = [[os.path.join(methyl_directory, "CpG_context_" + sample.name + ".readset_sorted.dedup.txt.gz")]]
            candidate_input_files.append([os.path.join(methyl_directory, "CpG_context_" + sample.name + ".sorted.dedup.txt.gz")])
            candidate_input_files.append([os.path.join(methyl_directory, "CpG_context_" + sample.name + ".sorted.txt.gz")])

            [cpG_input_file] = self.select_input_files(candidate_input_files)
            jobs.append(
                concat_jobs([
                    Job(command="mkdir -p " + methyl_directory),
                    bismark.bed_graph(
                        [cpG_input_file],
                        sample.name,
                        methyl_directory
                    )
                ], name = "bismark_bed_graph." + sample.name)
            )

        return jobs

    def methylation_profile(self):
        """
        """

        jobs = []
        for sample in self.samples:
            methyl_directory = os.path.join("methylation_call", sample.name)
            bismark_cov_file = os.path.join(methyl_directory, sample.name + ".bismark.cov.gz")

            jobs.append(
                concat_jobs([
                    Job(command="mkdir -p " + methyl_directory),
                    bismark.coverage2cytosine(
                        bismark_cov_file,
                        sample.name + ".bismark.cov.output",
                        methyl_directory
                    )
                ], name="methylation_profile." + sample.name)
           )

        return jobs

    def bis_snp(self):
        """
        """

        jobs = []
        for sample in self.samples:
            alignment_directory = os.path.join("alignment", sample.name)

            candidate_input_files = [[os.path.join(alignment_directory, sample.name + ".readset_sorted.dedup.bam")]]
            candidate_input_files.append([os.path.join(alignment_directory, sample.name + ".sorted.dedup.bam")])
            candidate_input_files.append([os.path.join(alignment_directory, sample.name + ".sorted.bam")])
            [input_file] = self.select_input_files(candidate_input_files)

            variant_directory = os.path.join("variants", sample.name)
            cpg_output_file = os.path.join(variant_directory, sample.name + ".cpg.vcf")
            snp_output_file = os.path.join(variant_directory, sample.name + ".snp.vcf")

            jobs.append(
                concat_jobs([
                    Job(command="mkdir -p " + variant_directory),
                    bissnp.bisulfite_genotyper(
                        input,
                        cpg_output_file,
                        snp_output_file
                    )
                ], name="bisSNP." + sample.name)
           )

        return jobs

    @property
    def steps(self):
        return [
            self.picard_sam_to_fastq,
            self.trimmomatic,
            self.merge_trimmomatic_stats,
            self.bismark_align,
            self.picard_add_read_groups,    # step 5
            self.picard_merge_sam_files,
            self.metrics,
            self.bismark_dedup,
            self.wiggle_tracks,
            self.puc19_lambda_reads,        # step 10
            self.methylation_call,
            self.bed_graph,
            self.methylation_profile,
            self.bis_snp,                   # step 14
        ]

if __name__ == '__main__': 
    MethylSeq()
