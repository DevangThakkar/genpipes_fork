#!/usr/bin/perl

=head1 NAME

I<dnaSeq>

=head1 SYNOPSIS

dnaSeq.pl

=head1 DESCRIPTION

B<dnaSeq> Is the main variant discovery pipeline.

=head1 AUTHOR

B<Louis Letourneau> - I<louis.letourneau@mail.mcgill.ca>

=head1 DEPENDENCY

B<Pod::Usage> Usage and help output.

B<Data::Dumper> Used to debbug

B<Config::Simple> Used to parse config file

B<File::Basename> path parsing

B<Cwd> path parsing

=cut

# Strict Pragmas
#---------------------
use strict;
use warnings;
#---------------------

BEGIN {
    # Add the mugqic_pipeline/lib/ path relative to this Perl script to @INC library search variable
    use File::Basename;
    use Cwd 'abs_path';
    my (undef, $mod_path, undef) = fileparse(abs_path(__FILE__));
    unshift @INC, $mod_path . "../../lib";
}


# Dependencies
#--------------------
use Getopt::Std;
use Cwd;
use POSIX;
use Cwd;

use BWA;
use GATK;
use IGVTools;
use LoadConfig;
use Picard;
use SampleSheet;
use SAMtools;
use SequenceDictionaryParser;
use SnpEff;
use SubmitToCluster;
use Trimmomatic;
use Tools;
use VCFtools;
use Metrics;
use GqSeqUtils;
#--------------------


# SUB
#--------------------

my @steps;
push(@steps, {'name' => 'trimAndAlign', 'stepLoop' => 'sample', 'parentStep' => undef});
push(@steps, {'name' => 'laneMetrics', 'stepLoop' => 'sample', 'parentStep' => 'trimAndAlign'});
push(@steps, {'name' => 'mergeTrimStats', 'stepLoop' => 'experiment', 'parentStep' => 'trimAndAlign'});
push(@steps, {'name' => 'mergeLanes', 'stepLoop' => 'sample', 'parentStep' => 'trimAndAlign'});
push(@steps, {'name' => 'indelRealigner', 'stepLoop' => 'sample', 'parentStep' => 'mergeLanes'});
push(@steps, {'name' => 'mergeRealigned', 'stepLoop' => 'sample', 'parentStep' => 'indelRealigner'});
push(@steps, {'name' => 'fixmate', 'stepLoop' => 'sample', 'parentStep' => 'mergeRealigned'});
push(@steps, {'name' => 'markDup', 'stepLoop' => 'sample', 'parentStep' => 'fixmate'});
push(@steps, {'name' => 'recalibration', 'stepLoop' => 'sample', 'parentStep' => 'markDup'});
push(@steps, {'name' => 'metrics', 'stepLoop' => 'sample', 'parentStep' => 'recalibration'});
push(@steps, {'name' => 'metricsLibrarySample', 'stepLoop' => 'experiment', 'parentStep' => 'metrics'});
push(@steps, {'name' => 'fullPileup', 'stepLoop' => 'sample', 'parentStep' => 'recalibration'});
push(@steps, {'name' => 'snpAndIndelBCF', 'stepLoop' => 'experiment', 'parentStep' => 'recalibration'});
push(@steps, {'name' => 'mergeFilterBCF', 'stepLoop' => 'experiment', 'parentStep' => 'snpAndIndelBCF'});
push(@steps, {'name' => 'filterNStretches', 'stepLoop' => 'experiment', 'parentStep' => 'mergeFilterBCF'});
push(@steps, {'name' => 'flagMappability', 'stepLoop' => 'experiment', 'parentStep' => 'mergeFilterBCF'});
push(@steps, {'name' => 'snpIDAnnotation', 'stepLoop' => 'experiment', 'parentStep' => 'flagMappability'});
push(@steps, {'name' => 'snpEffect', 'stepLoop' => 'experiment', 'parentStep' => 'snpIDAnnotation'});
push(@steps, {'name' => 'dbNSFPAnnotation', 'stepLoop' => 'experiment', 'parentStep' => 'snpEffect'});
push(@steps, {'name' => 'metricsSNV', 'stepLoop' => 'experiment', 'parentStep' => 'snpIDAnnotation'});
push(@steps, {'name' => 'deliverable' , 'stepLoop' => 'experiment' , 'parentStep' => ('metricsLanes','metricsSample','metricsSNV')});

my %globalDep;
for my $stepName (@steps) {
  $globalDep{$stepName -> {'name'} } ={};
}


# Global scope variables
my $configFile;
my $workDirectory = getcwd();


&main();

sub printUsage {
  print "\nUsage: perl ".$0." -c config.ini -s start -e end -n SampleSheet.csv\n";
  print "\t-c  config file\n";
  print "\t-s  start step, inclusive\n";
  print "\t-e  end step, inclusive\n";
  print "\t-n  nanuq sample sheet\n";
  print "\n";
  print "Steps:\n";
  for(my $idx=0; $idx < @steps; $idx++) {
    print "".($idx+1).'- '.$steps[$idx]->{'name'}."\n";
  }
  print "\n";
}

sub main {
  my %opts;
  getopts('c:s:e:n:', \%opts);
  
  if (!defined($opts{'c'}) || !defined($opts{'s'}) || !defined($opts{'e'}) || !defined($opts{'n'})) {
    printUsage();
    exit(1);
  }

  my %cfg = LoadConfig->readConfigFile($opts{'c'});
  my $rHoAoH_sampleInfo = SampleSheet::parseSampleSheetAsHash($opts{'n'});
  my $rAoH_seqDictionary = SequenceDictionaryParser::readDictFile(\%cfg);
  my $currentWorkDir = getcwd();
  $configFile =  abs_path($opts{'c'});

  my $latestBam;
  my @sampleNames = keys %{$rHoAoH_sampleInfo};

  print STDERR "Samples: ".scalar(@sampleNames)."\n";

  SubmitToCluster::initPipeline;

  my $currentStep;
  for(my $idx=0; $idx < @sampleNames; $idx++){
    my $sampleName = $sampleNames[$idx];
    my $rAoH_sampleLanes = $rHoAoH_sampleInfo->{$sampleName};

    for($currentStep = $opts{'s'}-1; $currentStep <= ($opts{'e'}-1); $currentStep++) {
      my $fname = $steps[$currentStep]->{'name'};
      my $subref = \&$fname;

      if ($steps[$currentStep]->{'stepLoop'} eq 'sample') {
        # Tests for the first step in the list. Used for dependencies.
        my $jobIdVar = &$subref($currentStep, \%cfg, $currentWorkDir, $sampleName, $rAoH_sampleLanes, $rAoH_seqDictionary); 
        $globalDep{$fname}->{$sampleName} = $jobIdVar;
      }
    }
  }  

  for($currentStep = $opts{'s'}-1; $currentStep <= ($opts{'e'}-1); $currentStep++) {
    if($steps[$currentStep]->{'stepLoop'} eq 'experiment') {
      my $fname = $steps[$currentStep]->{'name'};
      my $subref = \&$fname;

      my $jobIdVar = &$subref($currentStep, \%cfg, $rHoAoH_sampleInfo, $rAoH_seqDictionary);
      $globalDep{$fname}->{'experiment'} = $jobIdVar;
    }
  }
}

sub trimAndAlign {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  print "BWA_JOB_IDS=\"\"\n";
  my $setJobId = 0;
  for my $rH_laneInfo (@$rAoH_sampleLanes) {
    my $rgId = $rH_laneInfo->{'libraryBarcode'} . "_" . $rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'};
    my $rgSampleName = $rH_laneInfo->{'name'};
    my $rgLibrary = $rH_laneInfo->{'libraryBarcode'};
    my $rgPlatformUnit = $rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'};
    my $rgCenter = LoadConfig::getParam( $rH_cfg, 'aln', 'bwaInstitution' );

    my $outputDir = 'reads/'.$sampleName .'/run' .$rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'};
    print 'mkdir -p '.$outputDir."\n";
    my $ro_trimJob = Trimmomatic::trim($rH_cfg, $sampleName, $rH_laneInfo, $outputDir);
    SubmitToCluster::printSubmitCmd($rH_cfg, "trim", $rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'}, 'TRIM', undef, $sampleName, $ro_trimJob);

    my $outputAlnDir = 'alignment/'.$sampleName .'/run' .$rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'};
    print 'mkdir -p '.$outputAlnDir."\n";
    my $outputAlnPrefix = $outputAlnDir.'/'.$sampleName;

    my $useMem = LoadConfig::getParam($rH_cfg, 'aln', 'aligner') eq 'mem';
    if(!$useMem) {
      my $ro_bwaJob = BWA::aln($rH_cfg, $sampleName, $ro_trimJob->getOutputFileHash()->{PAIR1_OUTPUT}, $ro_trimJob->getOutputFileHash()->{PAIR2_OUTPUT},$ro_trimJob->getOutputFileHash()->{SINGLE1_OUTPUT}, $outputAlnPrefix, $rgId, $rgSampleName, $rgLibrary, $rgPlatformUnit, $rgCenter);
      if(!$ro_bwaJob->isUp2Date()) {
        if($ro_bwaJob->getNbCommands() == 3) {
            SubmitToCluster::printSubmitCmd($rH_cfg, "aln", 'read1.'.$rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'}, 'READ1ALN', $ro_trimJob->getCommandJobId(0), $sampleName, $ro_bwaJob, 0 );
            SubmitToCluster::printSubmitCmd($rH_cfg, "aln", 'read2.'.$rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'}, 'READ2ALN', $ro_trimJob->getCommandJobId(0), $sampleName, $ro_bwaJob, 1 );
            SubmitToCluster::printSubmitCmd($rH_cfg, "aln", 'sampe.'.$rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'}, 'BWA', $ro_bwaJob->getCommandJobId(0).LoadConfig::getParam($rH_cfg, 'aln', 'clusterDependencySep').$ro_bwaJob->getCommandJobId(1), $sampleName, $ro_bwaJob, 2 );
            print 'BWA_JOB_IDS=${BWA_JOB_IDS}'.LoadConfig::getParam($rH_cfg, 'aln', 'clusterDependencySep').$ro_bwaJob->getCommandJobId(2)."\n";
            $setJobId = 1;
        }
        else {
          SubmitToCluster::printSubmitCmd($rH_cfg, "aln", $rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'}, 'READALN', $ro_trimJob->getCommandJobId(0), $sampleName, $ro_bwaJob, 0 );
          SubmitToCluster::printSubmitCmd($rH_cfg, "aln", 'samse.'.$rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'}, 'BWA',  $ro_bwaJob->getCommandJobId(1), $sampleName, $ro_bwaJob, 1 );
          print 'BWA_JOB_IDS=${BWA_JOB_IDS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$ro_bwaJob->getCommandJobId(1)."\n";
          $setJobId = 1;
        } 
      }
    }
    else {
      my $ro_bwaJob = BWA::mem($rH_cfg, $sampleName, $ro_trimJob->getOutputFileHash()->{PAIR1_OUTPUT}, $ro_trimJob->getOutputFileHash()->{PAIR2_OUTPUT},$ro_trimJob->getOutputFileHash()->{SINGLE1_OUTPUT}, $outputAlnPrefix, $rgId, $rgSampleName, $rgLibrary, $rgPlatformUnit, $rgCenter);
      if(!$ro_bwaJob->isUp2Date()) {
        SubmitToCluster::printSubmitCmd($rH_cfg, "mem", $rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'}, 'BWA_MEM', $ro_trimJob->getCommandJobId(0), $sampleName, $ro_bwaJob);
        print 'BWA_JOB_IDS='.$ro_bwaJob->getCommandJobId(0)."\n";
        $setJobId = 1;
      }
    }
  }

  if($setJobId ==0){
    return undef;
  }

  return '$BWA_JOB_IDS';
}

sub laneMetrics {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }

  my $latestBam;
  my @inputBams;
  my $outputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.bam';
  print "LANE_METRICS_JOB_IDS=\"\"\n";
  my $first=1;
  for my $rH_laneInfo (@$rAoH_sampleLanes) {
    my $directory = 'alignment/'.$sampleName."/run".$rH_laneInfo->{'runId'}."_".$rH_laneInfo->{'lane'}."/";
    my $sortedLaneBamFile = $directory.$rH_laneInfo->{'name'}.".sorted.bam";
    my $sortedLaneDupBamFile = $directory.$rH_laneInfo->{'name'}.".sorted.dup.bam";
    my $outputMetrics = $directory.$rH_laneInfo->{'name'}.".sorted.dup.metrics";
    my $runName = $sampleName."_run".$rH_laneInfo->{'runId'}."_".$rH_laneInfo->{'lane'};

    my $rO_job = Picard::markDup($rH_cfg, $sampleName, $sortedLaneBamFile, $sortedLaneDupBamFile, $outputMetrics);
    if(!$rO_job->isUp2Date()) {
      SubmitToCluster::printSubmitCmd($rH_cfg, "markDup", $rH_laneInfo->{'runId'} . "_" . $rH_laneInfo->{'lane'}, 'LANEMARKDUP', $jobDependency, $sampleName, $rO_job);
      if($first == 1) {
        print 'LANE_METRICS_JOB_IDS='.$rO_job->getCommandJobId(0)."\n";
        $first = 0;
      }
      else {
        print 'LANE_METRICS_JOB_IDS=${LANE_METRICS_JOB_IDS}'.LoadConfig::getParam($rH_cfg, 'laneMarkDup', 'clusterDependencySep').$rO_job->getCommandJobId(0)."\n";
      }
    }
  }

  return '${LANE_METRICS_JOB_IDS}';
}

sub mergeTrimStats {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;

  my $libraryType =  undef;
  my $fkey =  (keys %{$rHoAoH_sampleInfo})[0] ;
  my @fvals = @{$rHoAoH_sampleInfo->{$fkey}};
  my $finfo = $fvals[0];
  if ( $finfo->{'runType'} eq "SINGLE_END" ) {
    $libraryType = 'single';
  } elsif ($finfo->{'runType'} eq "PAIRED_END" ) {
    $libraryType = 'paired';
  }
  my $trimmingDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};

  my @sampleNames = keys %{$rHoAoH_sampleInfo};
  my $jobDependencies = "";
  for(my $idx=0; $idx < @sampleNames; $idx++){
    my $sampleName = $sampleNames[$idx];
    my $rAoH_sampleLanes = $rHoAoH_sampleInfo->{$sampleName};
    if(defined($globalDep{$parentStep}->{$sampleName})){
      $jobDependencies .= LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$globalDep{$parentStep}->{$sampleName};
    }
  }
  if(length($jobDependencies) == 0) {
    $jobDependencies = undef;
  } else {
    $jobDependencies = substr($jobDependencies, 1);
  }
  $trimmingDependency = $jobDependencies;

  my $folder = 'reads';
  my $pattern = 'trim.stats.csv';
  my $ouputFile = 'metrics/trimming.stats';
  print "mkdir -p metrics\n";
  my $rO_job = Metrics::mergeTrimmomaticStats($rH_cfg,  $libraryType, $pattern, $folder, $ouputFile);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "trimMetrics", undef, 'TRIMMETRICS', $trimmingDependency, undef, $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}


sub mergeLanes {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }

  my $latestBam;
  my @inputBams;
  my $outputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.bam';
  for my $rH_laneInfo (@$rAoH_sampleLanes) {
    my $directory = 'alignment/'.$sampleName."/run".$rH_laneInfo->{'runId'}."_".$rH_laneInfo->{'lane'}."/";
    my $sortedLaneBamFile = $directory.$rH_laneInfo->{'name'}.".sorted.bam";
    my $runName = $sampleName."_run".$rH_laneInfo->{'runId'}."_".$rH_laneInfo->{'lane'};

    push(@inputBams, $sortedLaneBamFile);
  }

  my $rO_job = Picard::mergeFiles($rH_cfg, $sampleName, \@inputBams, $outputBAM);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "mergeLanes", undef, 'MERGELANES', $jobDependency, $sampleName, $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}

sub indelRealigner {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }
  print 'mkdir -p alignment/'.$sampleName."/realign\n";

  my $nbRealignJobs = LoadConfig::getParam( $rH_cfg, 'indelRealigner', 'nbRealignJobs' );
  if($nbRealignJobs > 50) {
    warn "Number of realign jobs is >50. This is usually much. Anything beyond 20 can be problematic.\n";
  }


  my $jobId;
  if($nbRealignJobs <= 1) {
    my $rO_job = GATK::realign($rH_cfg, $sampleName, 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.bam', undef, 'alignment/'.$sampleName.'/realign/all');
    if(!$rO_job->isUp2Date()) {
      SubmitToCluster::printSubmitCmd($rH_cfg, "indelRealigner", undef, 'REALIGN', $jobDependency, $sampleName, $rO_job);
      print 'REALIGN_JOB_IDS='.$rO_job->getCommandJobId(0)."\n";
      $jobId = '${REALIGN_JOB_IDS}';
    }
  }
  else {
    #Keep space for the exclude realignment at the end.
    $nbRealignJobs--;
    my @chrToProcess;
    for (my $idx=0; $idx < $nbRealignJobs; $idx++) {
      push(@chrToProcess, $rAoH_seqDictionary->[$idx]->{'name'});
    }

    print "REALIGN_JOB_IDS=\"\"\n";
    my $processUnmapped = 1;
    my @excludeList;
    for my $seqName (@chrToProcess) {
      push(@excludeList, $seqName);
      my $rO_job = GATK::realign($rH_cfg, $sampleName, 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.bam', $seqName, 'alignment/'.$sampleName.'/realign/'.$seqName, $processUnmapped);
      if(!$rO_job->isUp2Date()) {
        SubmitToCluster::printSubmitCmd($rH_cfg, "indelRealigner", $seqName, 'REALIGN', $jobDependency, $sampleName, $rO_job);
        if($processUnmapped == 1) {
          print 'REALIGN_JOB_IDS='.$rO_job->getCommandJobId(0)."\n";
          $processUnmapped = 0;
        }
        else {
          print 'REALIGN_JOB_IDS=${REALIGN_JOB_IDS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$rO_job->getCommandJobId(0)."\n";
        }
        $jobId = '${REALIGN_JOB_IDS}';
      }
    }

    my $rO_job = GATK::realign($rH_cfg, $sampleName, 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.bam', undef, 'alignment/'.$sampleName.'/realign/others', 1, \@excludeList);
    if(!$rO_job->isUp2Date()) {
      SubmitToCluster::printSubmitCmd($rH_cfg, "indelRealigner", 'others', 'REALIGN', $jobDependency, $sampleName, $rO_job);
      print 'REALIGN_JOB_IDS=${REALIGN_JOB_IDS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$rO_job->getCommandJobId(0)."\n";
      $jobId = '${REALIGN_JOB_IDS}';
    }
  }
  return $jobId;
}

sub mergeRealigned {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }

  my $jobId;
  my $latestBam;
  my @inputBams;
  my $outputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.realigned.qsorted.bam';

  my $nbRealignJobs = LoadConfig::getParam( $rH_cfg, 'indelRealigner', 'nbRealignJobs' );
  my $rO_job;
  if($nbRealignJobs <= 1) {
    my $command = 'if [ ! -e '.$outputBAM.' ]; then ln -s alignment/'.$sampleName.'/realign/all.bam '.$outputBAM.'; fi;';
    $rO_job = new Job(0);
    $rO_job->addCommand($command);
  }
  else {
    #Keep space for the exclude realignment at the end.
    $nbRealignJobs--;
    my @chrToProcess;
    for (my $idx=0; $idx < $nbRealignJobs; $idx++) {
      my $input = 'alignment/'.$sampleName.'/realign/'.$rAoH_seqDictionary->[$idx]->{'name'}.'.bam';
      push(@inputBams, $input);
    }
    push(@inputBams, 'alignment/'.$sampleName.'/realign/others.bam');

    $rO_job = Picard::mergeFiles($rH_cfg, $sampleName, \@inputBams, $outputBAM);
  }

  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "mergeRealign", undef, 'MERGEREALIGN', $jobDependency, $sampleName, $rO_job);
    $jobId = $rO_job->getCommandJobId(0);
  }

  return $jobId;
}

sub fixmate {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }

  my $inputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.realigned.qsorted.bam';
  my $outputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.matefixed.sorted.bam';

  my $rO_job = Picard::fixmate($rH_cfg, $inputBAM, $outputBAM);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "fixmate", undef, 'FIXMATE', $jobDependency, $sampleName, $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}

sub markDup {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }

  my $inputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.matefixed.sorted.bam';
  my $outputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.bam';
  my $outputMetrics = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.metrics';

  my $rO_job = Picard::markDup($rH_cfg, $sampleName, $inputBAM, $outputBAM, $outputMetrics);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "markDup", undef, 'MARKDUP', $jobDependency, $sampleName, $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}

sub recalibration {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }

  my $inputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.bam';
  my $outputBAM = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup';

  my $rO_job = GATK::recalibration($rH_cfg, $sampleName, $inputBAM, $outputBAM);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "recalibration", undef, 'RECAL', $jobDependency, $sampleName, $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}

sub metrics {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }

  my $rO_job;
  my $bamFile = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.recal.bam';
  my $jobId;

  # Collect metrics
  my $outputMetrics = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.recal.all.metrics';
  my $rO_collectMetricsJob = Picard::collectMetrics($rH_cfg, $bamFile, $outputMetrics);
  if(!$rO_collectMetricsJob->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "collectMetrics", undef, 'COLLECTMETRICS', $jobDependency, $sampleName, $rO_collectMetricsJob);
    if(!defined($jobId)) {
      $jobId='$METRICS_JOBS';
      print 'METRICS_JOBS='.$rO_collectMetricsJob->getCommandJobId(0)."\n";
    }
  }
  
  # Compute genome coverage
  my $outputPrefix = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.recal.all.coverage';
  my $rO_genomeCoverageJob = GATK::genomeCoverage($rH_cfg, $sampleName, $bamFile, $outputPrefix);
  if(!$rO_genomeCoverageJob->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "genomeCoverage", undef, 'GENOMECOVERAGE', $jobDependency, $sampleName, $rO_genomeCoverageJob);
    if(!defined($jobId)) {
      $jobId='$METRICS_JOBS';
      print 'METRICS_JOBS='.$rO_genomeCoverageJob->getCommandJobId(0)."\n";;
    }
    else {
      print 'METRICS_JOBS=${METRICS_JOBS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$rO_genomeCoverageJob->getCommandJobId(0)."\n";
    }
  }

  # Compute CCDS coverage
  $outputPrefix = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.recal.CCDS.coverage';
  my $rO_targetCoverageJob = GATK::targetCoverage($rH_cfg, $sampleName, $bamFile, $outputPrefix);
  if(!$rO_targetCoverageJob->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "targetCoverage", undef, 'TARGETCOVERAGE', $jobDependency, $sampleName, $rO_targetCoverageJob);
    if(!defined($jobId)) {
      $jobId='$METRICS_JOBS';
      print 'METRICS_JOBS='.$rO_targetCoverageJob->getCommandJobId(0)."\n";;
    }
    else {
      print 'METRICS_JOBS=${METRICS_JOBS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$rO_targetCoverageJob->getCommandJobId(0)."\n";
    }
  }

  # Generate IGV track
  my $rO_igvtoolsTDFJob = IGVTools::computeTDF($rH_cfg, $bamFile);
  if(!$rO_igvtoolsTDFJob->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "computeTDF", undef, 'IGVTOOLS', $jobDependency, $sampleName, $rO_igvtoolsTDFJob);
    if(!defined($jobId)) {
      $jobId='$METRICS_JOBS';
      print 'METRICS_JOBS='.$rO_igvtoolsTDFJob->getCommandJobId(0)."\n";
    }
    else {
      print 'METRICS_JOBS=${METRICS_JOBS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$rO_igvtoolsTDFJob->getCommandJobId(0)."\n";
    }
  }

  # Compute flags
  my $output = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.recal.bam.flagstat';
  my $rO_flagstatJob = SAMtools::flagstat($rH_cfg, $bamFile, $output);
  if(!$rO_flagstatJob->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "flagstat", undef, 'FLAGSTAT', $jobDependency, $sampleName, $rO_flagstatJob);
    if(!defined($jobId)) {
      $jobId='$METRICS_JOBS';
      print 'METRICS_JOBS='.$rO_flagstatJob->getCommandJobId(0)."\n";
    }
    else {
      print 'METRICS_JOBS=${METRICS_JOBS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$rO_flagstatJob->getCommandJobId(0)."\n";
    }
  }

  return $jobId;
}


sub metricsLibrarySample {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;
  
  
  my $metricsDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};

  my @sampleNames = keys %{$rHoAoH_sampleInfo};
  my $jobDependencies = "";
  for(my $idx=0; $idx < @sampleNames; $idx++){
    my $sampleName = $sampleNames[$idx];
    my $rAoH_sampleLanes = $rHoAoH_sampleInfo->{$sampleName};
    if(defined($globalDep{$parentStep}->{$sampleName})){
      $jobDependencies .= LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$globalDep{$parentStep}->{$sampleName};
    }
  }
  if(length($jobDependencies) == 0) {
    $jobDependencies = undef;
  } else {
    $jobDependencies = substr($jobDependencies, 1);
  }
  $metricsDependency = $jobDependencies;
  
  my $folder = 'alignment/';
  my $ouputFile = 'metrics/SampleMetrics.stats';
  my $experimentType = LoadConfig::getParam($rH_cfg, 'default', 'experimentType');
  print "mkdir -p metrics\n";

  my $rO_job = Metrics::mergeSampleDnaStats($rH_cfg,  $experimentType, $folder, $ouputFile);
  my $metricsJobId = undef;
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "sampleMetrics", undef, 'SAMPLEMETRICS', $metricsDependency, undef, $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}


sub sortQname {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }
}

#push(@steps, {'name' => 'countTelomere'});
sub fullPileup {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $currentWorkDir = shift;
  my $sampleName = shift;
  my $rAoH_sampleLanes  = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{$sampleName})) {
    $jobDependency = $globalDep{$parentStep}->{$sampleName};
  }

  my $bamFile = 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.recal.bam';
  my $outputDir = 'alignment/'.$sampleName.'/mpileup/';

  print 'mkdir -p '.$outputDir."\n";
  print "RAW_MPILEUP_JOB_IDS=\"\"\n";
  my $catCommand = 'zcat ';
  my $jobId;
  for my $rH_seqInfo (@$rAoH_seqDictionary) {
    my $seqName = $rH_seqInfo->{'name'};
    my $outputPerSeq = $outputDir.$sampleName.'.'.$seqName.'.mpileup.gz';
    my $rO_job = SAMtools::rawmpileup($rH_cfg, $sampleName, $bamFile, $seqName, $outputPerSeq);
    if(!$rO_job->isUp2Date()) {
      SubmitToCluster::printSubmitCmd($rH_cfg, "rawmpileup", $seqName, 'RAW_MPILEUP', $jobDependency, $sampleName, $rO_job);
      if(!defined($jobId)) {
        $jobId = '${RAW_MPILEUP_JOB_IDS}';
        print 'RAW_MPILEUP_JOB_IDS='.$rO_job->getCommandJobId(0)."\n";
      }
      else {
        print 'RAW_MPILEUP_JOB_IDS=${RAW_MPILEUP_JOB_IDS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$rO_job->getCommandJobId(0)."\n";
      }
    }

    $catCommand .= $outputPerSeq .' ';
  }

  if(defined($jobId)) {
    my $output = $outputDir.$sampleName.'.mpileup.gz';
    $catCommand .= '| gzip -c --best > '.$output;

    my $rO_job = new Job(0);
    $rO_job->addCommand($catCommand);

    SubmitToCluster::printSubmitCmd($rH_cfg, "rawmpileup_cat", undef, 'RAW_MPILEUP_CAT', '${RAW_MPILEUP_JOB_IDS}', $sampleName, $rO_job);
    return $rO_job->getCommandJobId(0);
  }
  return undef;
}

sub snpAndIndelBCF {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;

  my $parentStep = $steps[$stepId]->{'parentStep'};

  my @sampleNames = keys %{$rHoAoH_sampleInfo};
  my $jobDependencies = "";
  my @inputFiles;
  for(my $idx=0; $idx < @sampleNames; $idx++){
    my $sampleName = $sampleNames[$idx];
    my $rAoH_sampleLanes = $rHoAoH_sampleInfo->{$sampleName};
    if(defined($globalDep{$parentStep}->{$sampleName})){
      $jobDependencies .= LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$globalDep{$parentStep}->{$sampleName};
    }
    push(@inputFiles, 'alignment/'.$sampleName.'/'.$sampleName.'.sorted.dup.recal.bam');
  }
  if(length($jobDependencies) == 0) {
    $jobDependencies = undef;
  } else {
    $jobDependencies = substr($jobDependencies, 1);
  }

  my $outputDir = 'variants/rawBCF/';
  print 'mkdir -p '.$outputDir."\n";
  print "MPILEUP_JOB_IDS=\"\"\n";

  my $nbJobs = LoadConfig::getParam( $rH_cfg, 'mpileup', 'approxNbJobs' );
  my $rA_regions = generateApproximateWindows($nbJobs, $rAoH_seqDictionary);
  my $jobId;
  for my $region (@{$rA_regions}) {
    my $rO_job = SAMtools::mpileup($rH_cfg, 'allSamples', \@inputFiles, $region, $outputDir);
    if(!$rO_job->isUp2Date()) {
      $region =~ s/:/_/g;
      SubmitToCluster::printSubmitCmd($rH_cfg, "mpileup", $region, 'MPILEUP', $jobDependencies, 'allSamples', $rO_job);
      if(!defined($jobId)) {
        $jobId = '${MPILEUP_JOB_IDS}';
        print 'MPILEUP_JOB_IDS='.$rO_job->getCommandJobId(0)."\n";
      }
      else {
        print 'MPILEUP_JOB_IDS=${MPILEUP_JOB_IDS}'.LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$rO_job->getCommandJobId(0)."\n";
      }
    }
  }

  return $jobId;
}

sub generateApproximateWindows {
  my $nbJobs = shift;
  my $rAoH_seqDictionary = shift;

  my @retVal;
  if($nbJobs <= scalar(@{$rAoH_seqDictionary})) {
    for my $rH_seqInfo (@$rAoH_seqDictionary) {
      push(@retVal, $rH_seqInfo->{'name'}.':1-'.$rH_seqInfo->{'size'});
    }
  }
  else{
    $nbJobs -= @$rAoH_seqDictionary;
    my $totalSize = 0;
    for my $rH_seqInfo (@$rAoH_seqDictionary) {
      $totalSize += $rH_seqInfo->{'size'};
    }
    my $approxWindow = floor($totalSize / $nbJobs);

    for my $rH_seqInfo (@$rAoH_seqDictionary) {
      for(my $idx=1; $idx <= $rH_seqInfo->{'size'}; $idx += $approxWindow) {
        my $end = $idx+$approxWindow-1;
        if($end > $rH_seqInfo->{'size'}) {
          $end = $rH_seqInfo->{'size'};
        }

        my $region = $rH_seqInfo->{'name'}.':'.$idx.'-'.$end;
        push(@retVal, $region);
      }
    }
  }

#  my @retVal;
#  $totalSize = 0;
#  my $currentregion = "";
#  my $approxWindowRemaining = $approxWindow;
#  for my $rH_seqInfo (@$rAoH_seqDictionary) {
#    for(my $idx=1; $idx <= $rH_seqInfo->{'size'}; $idx += $approxWindowRemaining) {
#      my $end = $idx+$snvWindow-1;
#      my $hitEnd = 0;
#      if($end > $rH_seqInfo->{'size'}) {
#        $end = $rH_seqInfo->{'size'};
#        $hitEnd = 1;
#        $approxWindowRemaining -= ($end - $idx) +1;
#      }
#
#      my $region = $rH_seqInfo->{'name'}.':'.$idx.'-'.$end;
#      if(length($currentregion) == 0) {
#        $currentregion = $region;
#      }
#      else {
#        $currentregion .= ','.$region;
#      }
#
#      if($hitEnd == 0) {
#        push(@retVal, $currentregion);
#        $currentregion = "";
#        $approxWindowRemaining = $approxWindow;
#      }
#    }
#  }
#
#  if(length($currentregion) > 0) {
#    push(@retVal, $currentregion);
#  }

  return \@retVal;
}

sub mergeFilterBCF {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{'experiment'})) {
    $jobDependency = $globalDep{$parentStep}->{'experiment'};
  }

  my $nbJobs = LoadConfig::getParam( $rH_cfg, 'mpileup', 'approxNbJobs' );
  my $rA_regions = generateApproximateWindows($nbJobs, $rAoH_seqDictionary);

  my $bcfDir = 'variants/rawBCF/';
  my $outputDir = 'variants/';

  my $rO_job = SAMtools::mergeFilterBCF($rH_cfg, 'allSamples', $bcfDir, $outputDir, $rA_regions);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "mergeFilterBCF", undef, 'MERGEBCF', $jobDependency, 'allSamples', $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}

sub filterNStretches {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{'experiment'})) {
    $jobDependency = $globalDep{$parentStep}->{'experiment'};
  }

  my $inputVCF = 'variants/allSamples.merged.flt.vcf';
  my $outputVCF = 'variants/allSamples.merged.flt.NFiltered.vcf';

  my $rO_job = Tools::filterNStretches($rH_cfg, 'allSamples', $inputVCF, $outputVCF);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "filterNStretches", undef, 'FILTERN', $jobDependency, 'allSamples', $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}

sub flagMappability {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{'experiment'})) {
    $jobDependency = $globalDep{$parentStep}->{'experiment'};
  }

  my $inputVCF = 'variants/allSamples.merged.flt.NFiltered.vcf';
  my $outputVCF = 'variants/allSamples.merged.flt.mil.vcf';
  my $rO_job = VCFtools::annotateMappability($rH_cfg, $inputVCF, $outputVCF);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "flagMappability", undef, 'MAPPABILITY', $jobDependency, 'allSamples', $rO_job);
  }
  return $rO_job->getCommandJobId(0);
}

sub snpIDAnnotation {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{'experiment'})) {
    $jobDependency = $globalDep{$parentStep}->{'experiment'};
  }

  my $inputVCF = 'variants/allSamples.merged.flt.mil.vcf';
  my $vcfOutput = 'variants/allSamples.merged.flt.mil.snpId.vcf';

  my $rO_job = SnpEff::annotateDbSnp($rH_cfg, $inputVCF, $vcfOutput);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "snpIDAnnotation", undef, 'SNPID', $jobDependency, 'allSamples', $rO_job);
  }

  return $rO_job->getCommandJobId(0);
}

sub snpEffect {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};
  if(defined($globalDep{$parentStep}->{'experiment'})) {
    $jobDependency = $globalDep{$parentStep}->{'experiment'};
  }

  my $inputVCF = 'variants/allSamples.merged.flt.mil.snpId.vcf';
  my $vcfOutput = 'variants/allSamples.merged.flt.mil.snpId.snpeff.vcf';

  my $rO_job = SnpEff::computeEffects($rH_cfg, $inputVCF, $vcfOutput, 1);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "snpEffect", undef, 'SNPEFF', $jobDependency, 'allSamples', $rO_job);
  }

  return $rO_job->getCommandJobId(0);
}

sub dbNSFPAnnotation {
  my $depends = shift;
  my $rH_cfg = shift;
  my $rH_samplePair = shift;
  my $rAoH_seqDictionary = shift;

  my $jobDependency = undef;
  if($depends > 0) {
    $jobDependency = '${SNPEFF_JOB_ID}';
  }

  my $inputVCF = 'variants/allSamples.merged.flt.mil.snpId.snpeff.vcf';
  my $vcfOutput = 'variants/allSamples.merged.flt.mil.snpId.snpeff.dbnsfp.vcf';
  
  my $rO_job = SnpEff::annotateDbNSFP($rH_cfg, $inputVCF, $vcfOutput);
  if(!$rO_job->isUp2Date()) {
    SubmitToCluster::printSubmitCmd($rH_cfg, "dbNSFPAnnotation", undef, 'DBNSFP', $jobDependency, 'allSamples', $rO_job);
  }

  return $rO_job->getCommandJobId(0);
}

sub metricsSNV {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;

  my $vcfDependency = undef;
  my $parentStep = $steps[$stepId]->{'parentStep'};

  if(defined($globalDep{$parentStep}->{'experiment'})){
      $vcfDependency .= $globalDep{$parentStep}->{'experiment'};
  }
  
  
  my $inputVCF = 'variants/allSamples.merged.flt.mil.snpId.vcf';
  my $outputFile = 'metrics/allSamples.merged.flt.mil.snpId.snpeff.vcf.part.changeRate.tsv';
  my $listFiles='variants/allSamples.merged.flt.mil.snpId.snpeff.vcf.statsFile.txt';

  my $command = Metrics::svnStatsChangeRate($rH_cfg, $inputVCF, $outputFile, $listFiles);
  my $changeRateJobId = undef;
  if(defined($command) && length($command) > 0) {
    $changeRateJobId = SubmitToCluster::printSubmitCmd($rH_cfg, "metricsSNV", undef, 'CHANGERATE', $vcfDependency , 'allSamples', $command);
    $changeRateJobId = '$' .$changeRateJobId ;
  }
  
  my $outputBaseName='metrics/allSamples.SNV';
  $command = Metrics::svnStatsGetGraph($rH_cfg, $listFiles,$outputBaseName);
  
  my $snvGraphsJobId = undef;
  if(defined($command) && length($command) > 0) {
    $snvGraphsJobId = SubmitToCluster::printSubmitCmd($rH_cfg, "metricsSNV", undef, 'CHANGERATE', $vcfDependency , 'allSamples', $command);
    $snvGraphsJobId = '$' .$snvGraphsJobId ;
  }
  return $snvGraphsJobId
}


sub deliverable {
  my $stepId = shift;
  my $rH_cfg = shift;
  my $rHoAoH_sampleInfo = shift;
  my $rAoH_seqDictionary = shift;



  my $reportDependency = undef;
  my @parentStep = $steps[$stepId]->{'parentStep'};

  my $jobDependencies = "";
  for(my $idx=0; $idx < @parentStep; $idx++){
    my $stepName = $parentStep[$idx];
    if(defined($globalDep{$stepName}->{'experiment'})){
      $jobDependencies .= LoadConfig::getParam($rH_cfg, 'default', 'clusterDependencySep').$globalDep{$stepName}->{'experiment'};
    }
  }
  if(length($jobDependencies) == 0) {
    $jobDependencies = undef;
  } else {
    $jobDependencies = substr($jobDependencies, 1);
  }
  $reportDependency = $jobDependencies;


  my $command = GqSeqUtils::clientReport($rH_cfg,  $configFile, $workDirectory, 'DNAseq') ;

  my $deliverableJobId = undef;
  if(defined($command) && length($command) > 0) {
    $deliverableJobId = SubmitToCluster::printSubmitCmd($rH_cfg, "deliverable", 'REPORT', 'DNAREPORT', $reportDependency , 'allSamples', $command);
    $deliverableJobId = '$' .$deliverableJobId ;
  }

  return $deliverableJobId;
}


1;
