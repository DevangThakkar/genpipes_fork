#!/usr/bin/env python

# Python Standard Modules
import os

# MUGQIC Modules
from core.config import *
from core.job import *

def blasr(
    infile,
    infile_long,
    outfile,
    outfile_fofn,
    sam=False
    ):

    outfile_filtered = outfile + ".filtered"

    return  Job(
        [infile, infile_long],
        [outfile_filtered, outfile_fofn],
        [
            ['smrtanalysis_blasr', 'module_memtime'],
            ['smrtanalysis_blasr', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime blasr \\
  {infile} \\
  {infile_long} \\
  -out {outfile} \\
  -m {m} \\
  -nproc {threads} \\
  -bestn {bestn} \\
  -nCandidates {n_candidates} \\
  -noSplitSubreads \\
  -minReadLength {min_read_length} \\
  -maxScore {max_score} \\
  -maxLCPLength {max_lcp_length}{sam} && \\
echo {outfile} > {outfile_fofn} &&
filterm4.py {outfile} > {outfile_filtered} 2> {outfile_filtered}.log""".format(
        infile=infile,
        infile_long=infile_long,
        outfile=outfile,
        m=config.param('smrtanalysis_blasr', 'm', type='int'),
        threads=config.param('smrtanalysis_blasr', 'threads', type='posint'),
        bestn=config.param('smrtanalysis_blasr', 'bestn', type='int'),
        n_candidates=config.param('smrtanalysis_blasr', 'n_candidates', type='int'),
        min_read_length=config.param('smrtanalysis_blasr', 'min_read_length', type='int'),
        max_score=config.param('smrtanalysis_blasr', 'max_score', type='int'),
        max_lcp_length=config.param('smrtanalysis_blasr', 'max_lcp_length', type='int'),
        sam=" \\\n  -sam" if sam else "",
        outfile_fofn=outfile_fofn,
        outfile_filtered=outfile_filtered
    ))

def cmph5tools_sort(
    cmph5,
    cmph5_out
    ):

    return  Job(
        [cmph5],
        [cmph5_out],
        [
            ['smrtanalysis_cmph5tools_sort', 'module_memtime'],
            ['smrtanalysis_cmph5tools_sort', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime cmph5tools.py -vv sort --deep --inPlace \\
  --outFile {cmph5_out} \\
  {cmph5} \\
  > /dev/null""".format(
        cmph5=cmph5,
        cmph5_out=cmph5_out
    ))

def fastq_to_ca(
    libraryname,
    reads,
    outfile
    ):

    return  Job(
        [reads],
        [outfile],
        [
            ['smrtanalysis_fastq_to_ca', 'module_memtime'],
            ['smrtanalysis_fastq_to_ca', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime fastqToCA \\
  -technology sanger \\
  -type sanger \\
  -libraryname {libraryname} \\
  -reads {reads} \\
  > {outfile}""".format(
        libraryname=libraryname,
        reads=reads,
        outfile=outfile
    ))

def filtering(
    fofn,
    input_xml,
    params_xml,
    output_dir,
    log
    ):

    ref_params_xml=config.param('smrtanalysis_filtering', 'filtering_settings')
    output_prefix = os.path.join(output_dir, "data", "filtered_subreads.")
    input_fofn = os.path.join(output_dir, "input.fofn")
    output_fastq = output_prefix + "fastq"

    return Job(
        [fofn, ref_params_xml],
        [input_fofn, output_fastq, output_prefix + "fasta"],
        [
            ['smrtanalysis_filtering', 'module_memtime'],
            ['smrtanalysis_filtering', 'module_prinseq'],
            ['smrtanalysis_filtering', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime fofnToSmrtpipeInput.py {fofn} > {input_xml} && \\
cp {fofn} {input_fofn} && \\
memtime sed -e 's/MINSUBREADLENGTH/{min_subread_length}/g' -e 's/MINREADLENGTH/{min_read_length}/g' -e 's/MINQUAL/{min_qual}/g' \\
  < {ref_params_xml} > {params_xml} && \\
memtime smrtpipe.py \\
  -D NPROC={threads} \\
  -D TMP={tmp_dir} \\
  --params={params_xml} \\
  --output={output_dir} \\
  --debug \\
  xml:{input_xml} \\
  > {log} && \\
memtime prinseq-lite.pl \\
  -verbose \\
  -fastq {output_fastq} \\
  -out_format 1 \\
  -out_good {output_dir}/data/filtered_subreads""".format(
        fofn=fofn,
        input_fofn=input_fofn,
        input_xml=input_xml,
        min_subread_length=config.param('smrtanalysis_filtering', 'min_subread_length'),
        min_read_length=config.param('smrtanalysis_filtering', 'min_read_length'),
        min_qual=config.param('smrtanalysis_filtering', 'min_qual'),
        ref_params_xml=ref_params_xml,
        params_xml=params_xml,
        threads=config.param('smrtanalysis_filtering', 'threads'),
        tmp_dir=config.param('smrtanalysis_filtering', 'tmp_dir', type='dirpath'),
        output_dir=output_dir,
        log=log,
        output_fastq=output_fastq
    ))

def load_pulses(
    cmph5,
    input_fofn
    ):

    return  Job(
        [input_fofn, cmph5],
        # loadPulses modifies the input cmph5 directly
        [cmph5],
        [
            ['smrtanalysis_load_pulses', 'module_memtime'],
            ['smrtanalysis_load_pulses', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime loadPulses \\
  {input_fofn} \\
  {cmph5} \\
  -metrics DeletionQV,IPD,InsertionQV,PulseWidth,QualityValue,MergeQV,SubstitutionQV,DeletionTag -byread""".format(
        input_fofn=input_fofn,
        cmph5=cmph5
    ))

def m4topre(
    infile,
    allm4,
    subreads,
    outfile
    ):

    return  Job(
        [infile],
        [outfile],
        [
            ['smrtanalysis_m4topre', 'module_memtime'],
            ['smrtanalysis_m4topre', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime m4topre.py \\
  {infile} \\
  {allm4} \\
  {subreads} \\
  {bestn} \\
  > {outfile}""".format(
        infile=infile,
        allm4=allm4,
        subreads=subreads,
        bestn=config.param('smrtanalysis_m4topre', 'bestn', type='int'),
        outfile=outfile
    ))

def pbalign(
    cmph5,
    control_regions_fofn,
    input_fofn,
    ref_upload,
    tmp_dir
    ):

    return  Job(
        [input_fofn, ref_upload],
        [cmph5],
        [
            ['smrtanalysis_pbalign', 'module_memtime'],
            ['smrtanalysis_pbalign', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime pbalign.py \\
  {input_fofn} \\
  {ref_upload} \\
  {cmph5} \\
   --seed=1 --minAccuracy=0.75 --minLength=50 --algorithmOptions="-useQuality" --algorithmOptions=" -minMatch 12 -bestn 10 -minPctIdentity 70.0" --hitPolicy=randombest \\
  --tmpDir={tmp_dir} \\
  -vv \\
  --nproc={threads} \\
  --regionTable={control_regions_fofn}""".format(
        input_fofn=input_fofn,
        ref_upload=ref_upload,
        cmph5=cmph5,
        tmp_dir=tmp_dir,
        threads=config.param('smrtanalysis_pbalign', 'threads', type='posint'),
        control_regions_fofn=control_regions_fofn
    ))

def pbdagcon(
    infile,
    outfile,
    outfile_fastq
    ):

    return  Job(
        [infile],
        [outfile, outfile_fastq],
        [
            ['smrtanalysis_pbdagcon', 'module_memtime'],
            ['smrtanalysis_pbdagcon', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime pbdagcon -a -j {threads} \\
  {infile} \\
  > {outfile} && \\
awk '{{if ($0~/>/) {{sub(/>/,"@",$0);print;}} else {{l=length($0);q=""; while (l--) {{q=q "9"}}printf("%s\\n+\\n%s\\n",$0,q)}}}}' {outfile} \\
  > {outfile_fastq}""".format(
        threads=config.param('smrtanalysis_pbdagcon', 'threads', type='posint'),
        infile=infile,
        outfile=outfile,
        outfile_fastq=outfile_fastq
    ))

def pbutgcns(
    gpk_store,
    tig_store,
    unitigs_list,
    prefix,
    outdir,
    outfile,
    tmp_dir
    ):

    return  Job(
        [gpk_store, tig_store],
        [outfile],
        [
            ['smrtanalysis_pbutgcns', 'module_memtime'],
            ['smrtanalysis_pbutgcns', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime tigStore \\
  -g {gpk_store} \\
  -t {tig_store} 1 \\
  -d properties -U | \\
awk 'BEGIN{{t=0}}$1=="numFrags"{{if ($2 > 1) {{print t, $2}} t++}}' | sort -nrk2,2 \\
  > {unitigs_list} && \\
mkdir -p {outdir} && \\
tmp={tmp_dir} \\
cap={prefix} \\
utg={unitigs_list} \\
nprocs={threads} \\
cns={outfile} \\
pbutgcns_wf.sh""".format(
        gpk_store=gpk_store,
        tig_store=tig_store,
        unitigs_list=unitigs_list,
        outdir=outdir,
        tmp_dir=tmp_dir,
        prefix=prefix,
        threads=config.param('smrtanalysis_pbutgcns', 'threads', type='posint'),
        outfile=outfile
    ))

def reference_uploader(
    prefix,
    sample_name,
    fasta
    ):

    return  Job(
        [fasta],
        [os.path.join(prefix, sample_name, "sequence", sample_name + ".fasta")],
        [
            ['smrtanalysis_reference_uploader', 'module_memtime'],
            ['smrtanalysis_reference_uploader', 'module_smrtanalysis']
        ],
        # Preload assembled contigs as reference
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime referenceUploader \\
  --skipIndexUpdate \\
  -c \\
  -p {prefix} \\
  -n {sample_name} \\
  -f {fasta} \\
  --saw="sawriter -blt 8 -welter" --jobId="Anonymous" \\
  --samIdx="samtools faidx" --jobId="Anonymous" --verbose""".format(
        prefix=prefix,
        sample_name=sample_name,
        fasta=fasta
    ))

def run_ca(
    infile,
    ini,
    prefix,
    outdir
    ):

    return  Job(
        [infile, ini],
        [
            os.path.join(outdir, prefix + ".ovlStore.list"),
            os.path.join(outdir, prefix + ".tigStore"),
            os.path.join(outdir, prefix + ".gkpStore")
        ],
        [
            ['smrtanalysis_run_ca', 'module_memtime'],
            ['smrtanalysis_run_ca', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime runCA \\
  -s {ini} \\
  -p {prefix} \\
  -d {outdir} \\
  {infile}""".format(
        infile=infile,
        ini=ini,
        prefix=prefix,
        outdir=outdir
    ))

def summarize_polishing(
    sample_name,
    reference,
    aligned_reads_cmph5,
    alignment_summary,
    coverage_bed,
    aligned_reads_sam,
    variants_gff,
    variants_bed,
    variants_vcf
    ):

    return  Job(
        [aligned_reads_cmph5, os.path.join(os.path.dirname(reference), "data", "consensus.fasta")],
        [variants_vcf],
        [
            ['smrtanalysis_run_ca', 'module_memtime'],
            ['smrtanalysis_run_ca', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime summarizeCoverage.py \\
  --reference {reference} \\
  --numRegions=500 \\
  {aligned_reads_cmph5} \\
  > {alignment_summary} && \\
memtime gffToBed.py \\
  --name=meanCoverage \\
  --description="Mean coverage of genome in fixed interval regions" \\
  coverage {alignment_summary} \\
  > {coverage_bed} && \\
memtime loadSequencingChemistryIntoCmpH5.py \\
  --xml {chemistry_mapping} \\
  --h5 {aligned_reads_cmph5} && \\
memtime h5repack -f GZIP=1 \\
  {aligned_reads_cmph5} \\
  {aligned_reads_cmph5}.repacked && \\
mv {aligned_reads_cmph5}.repacked {aligned_reads_cmph5} && \\
memtime pbsamtools.py --bam \\
  --outfile {aligned_reads_sam} \\
  --refrepos {reference} \\
  --readGroup movie {aligned_reads_cmph5} && \\
memtime cmph5tools.py -vv sort --deep --inPlace {aligned_reads_cmph5} && \\
memtime summarizeConsensus.py \\
  --variantsGff {variants_gff} \\
  {alignment_summary} \\
  --output {alignment_summary}.tmp && \\
mv {alignment_summary}.tmp {alignment_summary} && \\
memtime gffToBed.py --name=variants \\
  --description='PacBio: snps, insertions, and deletions derived from consensus calls against reference' \\
  variants {variants_gff} \\
  > {variants_bed} && \\
memtime gffToVcf.py \\
  --globalReference={sample_name} \\
  {variants_gff} \\
  > {variants_vcf}""".format(
        reference=reference,
        aligned_reads_cmph5=aligned_reads_cmph5,
        alignment_summary=alignment_summary,
        coverage_bed=coverage_bed,
        chemistry_mapping=config.param('smrtanalysis_summarize_polishing', 'chemistry_mapping', type='filepath'),
        aligned_reads_sam=aligned_reads_sam,
        variants_gff=variants_gff,
        variants_bed=variants_bed,
        sample_name=sample_name,
        variants_vcf=variants_vcf
    ))

def variant_caller(
    cmph5,
    ref_fasta,
    outfile_variants,
    outfile_fasta,
    outfile_fastq
    ):

    outfile_fasta_uncompressed = re.sub("\.(gz|gzip)$", "", outfile_fasta)

    return  Job(
        [cmph5, ref_fasta],
        [outfile_variants, outfile_fasta, outfile_fastq, re.sub("\.gz$", "", outfile_fasta_uncompressed)],
        [
            ['smrtanalysis_variant_caller', 'module_memtime'],
            ['smrtanalysis_variant_caller', 'module_smrtanalysis']
        ],
        command = """\
set +u && source $SEYMOUR_HOME/etc/setup.sh && set -u && \\
memtime variantCaller.py \\
  -P {protocol} \\
  -v \\
  -j {threads} \\
  --algorithm={algorithm} \\
  {cmph5} \\
  -r {ref_fasta} \\
  -o {outfile_variants} \\
  -o {outfile_fasta} \\
  -o {outfile_fastq} \\
  > /dev/null && \\
gunzip -c \\
  {outfile_fasta} \\
  > {outfile_fasta_uncompressed}""".format(
        protocol=config.param('smrtanalysis_variant_caller', 'protocol', type='dirpath'),
        threads=config.param('smrtanalysis_variant_caller', 'threads', type='posint'),
        algorithm=config.param('smrtanalysis_variant_caller', 'algorithm'),
        cmph5=cmph5,
        ref_fasta=ref_fasta,
        outfile_variants=outfile_variants,
        outfile_fasta=outfile_fasta,
        outfile_fastq=outfile_fastq,
        outfile_fasta_uncompressed=outfile_fasta_uncompressed
    ))
