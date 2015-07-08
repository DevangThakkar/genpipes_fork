#!/usr/bin/env python

# Python Standard Modules
import logging
import os

# MUGQIC Modules
from core.config import *
from core.job import *

log = logging.getLogger(__name__)

def catenate(
	input_fastq,
	input_name,
	catenate_fasta
	):

	inputs = input_fastq
	outputs = [catenate_fasta]

	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/split_libraries_fastq.py \\
  -i {input_files} \\
  --sample_id {sample_name} \\
  -o {dir_output} \\
  -r 30 \\
  -p 0.01 \\
  -n 100 \\
  --barcode_type 'not-barcoded'""".format(
		input_files=','.join(input_fastq),
		sample_name=','.join(input_name),
		dir_output="catenate/",
		),
		removable_files=[catenate_fasta]
	)

def uchime(
	cat_sequence_fasta,
	chimeras_split_directory,
	chimeras_split_file
	):

	inputs = [cat_sequence_fasta]
	outputs = [chimeras_split_file]

	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime'],
			['qiime', 'module_usearch61']
		],

		command="""\
  $QIIME_HOME/identify_chimeric_seqs.py \\
  -i {cat_sequence_fasta} \\
  -m {usearch61} \\
  -r {database} \\
  --threads {threads_number} \\
  -o {chimeras_split_directory}""".format(
		cat_sequence_fasta=cat_sequence_fasta,
		usearch61="usearch61",
		database=config.param('qiime', 'chimera_database'),
		threads_number=config.param('qiime', 'threads'),
		chimeras_split_directory=chimeras_split_directory
		),
		removable_files=[chimeras_split_file]
	)
	
def filter_chimeras(
	cat_sequence_fasta,
	chimeras_file,
	filter_fasta
	):

	inputs = [cat_sequence_fasta, chimeras_file]
	outputs = [filter_fasta]

	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/filter_fasta.py \\
  -f {cat_sequence_fasta} \\
  -s {chimeras_file} \\
  -n \\
  -o {filter_fasta}""".format(
		cat_sequence_fasta=cat_sequence_fasta,
		filter_fasta=filter_fasta,
		chimeras_file=chimeras_file
		),
		removable_files=[filter_fasta]
	)

def otu_picking(
	input_without_chimer,
	output_directory,
	output_otus
	):

	inputs = [input_without_chimer]
	outputs = [output_otus]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/pick_otus.py \\
  -i {input_without_chimer} \\
  -m {method} \\
  -s {similarity_treshold} \\
  --threads {threads_number} \\
  -o {output_directory}""".format(
		input_without_chimer=input_without_chimer,
		method='sumaclust',
		similarity_treshold=config.param('qiime', 'similarity'),
		threads_number=config.param('qiime', 'threads'),
		output_directory=output_directory
		),
		removable_files=[output_otus]
	)

		
def otu_rep_picking(
	otu_file,
	filter_fasta,
	output_directory,
	otu_rep_file
	):

	inputs = [otu_file, filter_fasta]
	outputs = [otu_rep_file]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/pick_rep_set.py \\
  -i {otu_file} \\
  -f {filter_fasta} \\
  -m {method} \\
  -o {output_directory}""".format(
		otu_file=otu_file,
		filter_fasta=filter_fasta,
		method=config.param('qiime', 'rep_set_picking_method'),
		output_directory=otu_rep_file
		),
		removable_files=[otu_rep_file]
	)
			
def otu_assigning(
	otu_rep_picking_fasta,
	output_directory,
	tax_assign_file
	):

	inputs = [otu_rep_picking_fasta]
	outputs = [tax_assign_file]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/parallel_assign_taxonomy_uclust.py \\
  -i {otu_rep_picking_fasta} \\
  -T \\
  -O {threads_number} \\
  -r {database_otus} \\
  -t {taxonomy_otus} \\
  -o {output_directory}""".format(
		otu_rep_picking_fasta=otu_rep_picking_fasta,
		threads_number=config.param('qiime', 'threads'),
		database_otus=config.param('qiime', 'reference_seqs_fp'),
		taxonomy_otus=config.param('qiime', 'id_to_taxonomy_fp'),
		output_directory=output_directory
		),
		removable_files=[tax_assign_file]
	)
			
				
def otu_table(
	otu_file,
	tax_assign_file,
	otu_directory,
	otu_table_file,
	otu_table_summary
	):

	inputs = [otu_file, tax_assign_file]
	outputs = [otu_table_file,otu_table_summary]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/make_otu_table.py \\
  -i {otu_file} \\
  -t {tax_assign_file} \\
  -o {otu_table_file}""".format(
		otu_file=otu_file,
		tax_assign_file=tax_assign_file,
		otu_table_file=otu_table_file
		),
		removable_files=[otu_table_file,otu_table_summary]
	)

def otu_alignment(
	otu_rep_picking_fasta,
	output_directory,
	align_seq_fasta
	):

	inputs = [otu_rep_picking_fasta]
	outputs = [align_seq_fasta]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/parallel_align_seqs_pynast.py \\
  -i {otu_rep_picking_fasta} \\
  -T \\
  --jobs_to_start {threads_number} \\
  -o {output_directory}""".format(
		otu_rep_picking_fasta=otu_rep_picking_fasta,
		threads_number=config.param('qiime', 'threads'),
		output_directory=output_directory
		),
		removable_files=[align_seq_fasta]
	)
	
def filter_alignment(
	align_seq_fasta,
	output_directory,
	filter_align_fasta
	):

	inputs = [align_seq_fasta]
	outputs = [filter_align_fasta]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/filter_alignment.py \\
  -i {align_seq_fasta} \\
  -o {output_directory}""".format(
		align_seq_fasta=align_seq_fasta,
		output_directory=output_directory
		),
		removable_files=[filter_align_fasta]
	)	

def phylogeny(
	filter_align_fasta,
	output_directory,
	phylo_file
	):

	inputs = [filter_align_fasta]
	outputs = [phylo_file]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/make_phylogeny.py \\
  -i {filter_align_fasta} \\
  -o {output_directory}""".format(
		filter_align_fasta=filter_align_fasta,
		output_directory=phylo_file
		),
		removable_files=[phylo_file]
	)	
	
def multiple_rarefaction(
	otus_input,
	rarefied_otu_directory
	):

	inputs = otus_input
	outputs = [rarefied_otu_directory]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/multiple_rarefactions.py \\
  -i {otus_input} \\
  -m {multiple_rarefaction_min} \\
  -x {multiple_rarefaction_max} \\
  -s {multiple_rarefaction_step} \\
  -n 3 \\
  --output_path {rarefied_otu_directory}""".format(
		otus_input=otus_input[0],
		multiple_rarefaction_min=config.param('qiime', 'multiple_rarefaction_min'),
		multiple_rarefaction_max=config.param('qiime', 'multiple_rarefaction_max'),
		multiple_rarefaction_step=config.param('qiime', 'multiple_rarefaction_step'),
		rarefied_otu_directory=rarefied_otu_directory
		),
		removable_files=[rarefied_otu_directory]
	)
				
def alpha_diversity(
	rarefied_otu_directory,
	alpha_diversity_directory
	):

	inputs = [rarefied_otu_directory]
	outputs = [alpha_diversity_directory]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/alpha_diversity.py \\
  -i {rarefied_otu_directory} \\
  -m {metrics} \\
  -o {alpha_diversity_directory}""".format(
		rarefied_otu_directory=rarefied_otu_directory,
		metrics="observed_species,chao1,shannon",
		alpha_diversity_directory=alpha_diversity_directory
		),
		removable_files=[alpha_diversity_directory]
	)

def collate_alpha(
	alpha_diversity_directory,
	alpha_diversity_collated_merge_directory,
	chao1_stat,
	observed_species_stat,
	shannon_stat
	):

	inputs = [alpha_diversity_directory]
	outputs = [chao1_stat,observed_species_stat,shannon_stat]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/collate_alpha.py \\
  -i {alpha_diversity_directory} \\
  -o {alpha_diversity_collated_merge_directory}""".format(
		alpha_diversity_directory=alpha_diversity_directory,
		alpha_diversity_collated_merge_directory=alpha_diversity_collated_merge_directory
		),
		removable_files=[chao1_stat,observed_species_stat,shannon_stat]
	)
				
def sample_rarefaction_plot(
	chao1_stat,
	observed_species_stat,
	shannon_stat,
	sample_collated_directory,	
	sample_map,
	sample_rarefaction_directory,
	curve_sample
	):

	inputs = [chao1_stat,observed_species_stat,shannon_stat]
	outputs = [sample_rarefaction_directory] + curve_sample
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/make_rarefaction_plots.py \\
  -i {sample_collated_directory} \\
  -m {sample_map}\\
  -o {sample_rarefaction_directory}""".format(
		sample_collated_directory=sample_collated_directory,
		sample_map=sample_map,
		sample_rarefaction_directory=sample_rarefaction_directory
		),
		removable_files=[sample_rarefaction_directory]
	)

def single_rarefaction(
	otu_table,
	chao1_rarefied_stat,
	observed_species_rarefied_stat,
	shannon_rarefied_stat,
	otu_even_table
	):

	inputs = [otu_table]
	outputs = [chao1_rarefied_stat,observed_species_rarefied_stat,shannon_rarefied_stat,otu_even_table]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/single_rarefaction.py \\
  -i {otu_table} \\
  -o {otu_even_table} \\
  -d {depth}""".format(
		otu_table=otu_table,
		otu_even_table=otu_even_table,
		depth=config.param('qiime', 'single_rarefaction_depth')
		),
		removable_files=[otu_even_table]
	)
	
def rarefaction_plot(
	alpha_diversity_collated_merge_rarefied_directory,
	chao1_stat,
	observed_species_stat,
	shannon_stat,
	map_file,
	alpha_diversity_rarefaction_file,
	alpha_diversity_rarefaction_rarefied_directory
	):

	inputs = [chao1_stat,observed_species_stat,shannon_stat]
	outputs = [alpha_diversity_rarefaction_file]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/make_rarefaction_plots.py \\
  -i {alpha_diversity_collated_merge_rarefied_directory} \\
  -m {map_file}\\
  -o {alpha_diversity_rarefaction_rarefied_directory}""".format(
		alpha_diversity_collated_merge_rarefied_directory=alpha_diversity_collated_merge_rarefied_directory,
		map_file=map_file,
		alpha_diversity_rarefaction_rarefied_directory=alpha_diversity_rarefaction_rarefied_directory
		),
		removable_files=[alpha_diversity_rarefaction_file]
	)

	
def summarize_taxa(
	otus_input,
	taxonomic_directory,
	taxonomic_phylum,
	taxonomic_class,
	taxonomic_order,
	taxonomic_family,
	taxonomic_genus
	):

	inputs = otus_input
	outputs = [taxonomic_directory, taxonomic_phylum, taxonomic_class, taxonomic_order, taxonomic_family, taxonomic_genus]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/summarize_taxa.py \\
  -i {otus_input} \\
  -a \\
  -o {taxonomic_directory}""".format(
		otus_input=otus_input[0],
		taxonomic_directory=taxonomic_directory
		),
		removable_files=[taxonomic_directory, taxonomic_phylum, taxonomic_class, taxonomic_order, taxonomic_family, taxonomic_genus]
	)

def plot_taxa(
	taxonomic_input,
	alpha_diversity_taxonomy_bar_plot,
	taxonomic_directory
	):

	inputs = taxonomic_input
	outputs = [alpha_diversity_taxonomy_bar_plot]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/plot_taxa_summary.py \\
  -i {taxonomic_input} \\
  -l {label} \\
  -y 10 \\
  -t png \\
  -c {chart_type} \\
  -o {taxonomic_directory}""".format(
		taxonomic_input=",".join(taxonomic_input),
		label="Phylum,Class,Order,Family,Genus",
		chart_type="bar",
		taxonomic_directory=taxonomic_directory
		),
		removable_files=[alpha_diversity_taxonomy_bar_plot]
	)
		
def krona(
	otus_input,
	sample_name,
	alpha_diversity_krona_file
	):

	inputs = otus_input
	outputs = [alpha_diversity_krona_file]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime'],
			['qiime', 'module_krona']
		],

		command="""\
  ktImportText \\
  {sample_name} \\
  -o {alpha_diversity_krona_file}""".format(
		sample_name=' '.join(sample_name),
		alpha_diversity_krona_file=alpha_diversity_krona_file
		),
		removable_files=[alpha_diversity_krona_file]
	)

def beta_diversity(
	otu_even_table,
	phylogenetic_tree_file,
	dm_directory,
	dm_unweighted_file,
	dm_weighted_file
	):

	inputs = [otu_even_table, phylogenetic_tree_file]
	outputs = [dm_unweighted_file,dm_weighted_file]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/beta_diversity.py \\
  -i {otu_even_table} \\
  -t {phylogenetic_tree_file} \\
  -o {dm_directory}""".format(
		otu_even_table=otu_even_table,
		phylogenetic_tree_file=phylogenetic_tree_file,
		dm_directory=dm_directory
		),
		removable_files=[dm_unweighted_file,dm_weighted_file]
	)

def pcoa(
	dm_unweighted_file,
	dm_weighted_file,
	dm_directory,
	pcoa_directory,
	pcoa_unweighted_file,
	pcoa_weighted_file
	):

	inputs = [dm_unweighted_file, dm_weighted_file]
	outputs = [pcoa_unweighted_file,pcoa_weighted_file]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/principal_coordinates.py \\
  -i {dm_directory} \\
  -o {pcoa_directory}""".format(
		dm_directory=dm_directory,
		pcoa_directory=pcoa_directory
		),
		removable_files=[pcoa_directory]
	)

def pcoa_plot(
	pcoa_file,
	pcoa_directory,
	map_file,
	beta_diversity_pcoa,
	pcoa_plot_directory
	):

	inputs = [pcoa_file]
	outputs = [beta_diversity_pcoa]
	
	return Job(
		inputs,
		outputs,
		[
			['qiime', 'module_qiime']
		],

		command="""\
  $QIIME_HOME/make_2d_plots.py \\
  -i {pcoa_file} \\
  -m {map_file} \\
  -o {pcoa_plot_directory}""".format(
		pcoa_file=pcoa_file,
		map_file=map_file,
		pcoa_plot_directory=pcoa_plot_directory
		),
		removable_files=[beta_diversity_pcoa]
	)
															