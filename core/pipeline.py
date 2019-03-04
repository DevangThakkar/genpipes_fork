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

# Check Python version
import sys
if sys.version_info < (2,7):
    raise SystemExit("Incompatible Python version: " + sys.version + "\nPython 2.7 or higher is required")

# Python Standard Modules
import argparse
import collections
import datetime
import hashlib
import logging
import os
import re
import textwrap
from uuid import uuid4

# MUGQIC Modules
from config import config
from job import *
from scheduler import *
from step import *

from bfx import jsonator
from graphviz import Digraph

log = logging.getLogger(__name__)

class Pipeline(object):
    def __init__(self):
        self._timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self._args = self.argparser.parse_args()
        if self.protocol is None:
            step_list = self.steps
        elif self.args.help:
            step_list = []
            for i in range(0, len(self.protocol)):
                step_list = step_list + self.steps[i]
            tmp_set_list = {}
            step_list = [tmp_set_list.setdefault(step, step) for step in step_list if step not in tmp_set_list]
        else:
            pos = 0
            for i in range(0, len(self.protocol)):
                if self.protocol[i] == self.args.type:
                    pos = i
            step_list = self.steps[pos]
        logging.basicConfig(level=getattr(logging, self.args.log.upper()))

        if self.args.help:
            print textwrap.dedent("""\
              [TOC]

              {pipeline_doc}

              Usage
              -----
              ```
              #!text

              {help}
              ```
              {step_doc}
            """).format(
            pipeline_doc=textwrap.dedent(self.__doc__ or ""),
            help=self.argparser.format_help(),
            overview=self.__doc__ or "",
            #step_doc="\n".join([str(idx + 1) + "- " + step.__name__ + "\n" + "-" * len(str(idx + 1) + "- " + step.__name__) + (textwrap.dedent(step.__doc__) if step.__doc__ else "") for idx, step in enumerate(step_list)])
            step_doc="\n".join([step.__name__ + "\n" + "-" * len(step.__name__) + (textwrap.dedent(step.__doc__) if step.__doc__ else "") for step in step_list])
            )
            self.argparser.exit()

        # Normal pipeline execution
        if self.args.config:
            config.parse_files(self.args.config)
        else:
            self.argparser.error("argument -c/--config is required!")

        # Create a config trace from merged config file values
        with open(self.__class__.__name__ + ".config.trace.ini", 'wb') as config_trace:
            config_trace.write(textwrap.dedent("""\
              # {self.__class__.__name__} Config Trace
              # Created on: {self.timestamp}
              # From:
              #   {config_files}
              # DO NOT EDIT THIS AUTOMATICALLY GENERATED FILE - edit the master config files

            """).format(config_files="\n#   ".join([config_file.name for config_file in self.args.config]), self=self))
            config.write(config_trace)
            config.filepath = os.path.abspath(config_trace.name)

        self._output_dir = os.path.abspath(self.args.output_dir)
        self._scheduler = create_scheduler(self.args.job_scheduler, self.args.config)

        step_counter = collections.Counter(step_list)
        duplicated_steps = [step.__name__ for step in step_counter if step_counter[step] > 1]
        if duplicated_steps:
            raise Exception("Error: pipeline contains duplicated steps: " + ", ".join(duplicated_steps) + "!")
        else:
            self._step_list = [Step(step) for step in step_list]

        if self.args.steps:
            if re.search("^\d+([,-]\d+)*$", self.args.steps):
                if max(parse_range(self.args.steps)) > len(step_list):
                    raise Exception("You are trying to access a non-existing step.")
                self._step_range = [self.step_list[i - 1] for i in parse_range(self.args.steps)]
                self._step_range_num = [i for i in parse_range(self.args.steps)]
            else:
                raise Exception("Error: step range \"" + self.args.steps +
                    "\" is invalid (should match \d+([,-]\d+)*)!")
        else:
            self.argparser.error("argument -s/--steps is required!")

        self._sample_list = []
        self._sample_paths = []

        # For job reporting, all jobs must be created first, no matter whether they are up to date or not
        if self.args.report:
            self._force_jobs = True
            self.create_jobs()
            self.report_jobs()
        # For job cleaning, all jobs must be created first, no matter whether they are up to date or not
        elif self.args.clean:
            self._force_jobs = True
            self.create_jobs()
            self.clean_jobs()
        else:
            self._force_jobs = self.args.force
            self.create_jobs()
            self.submit_jobs()

    # Pipeline command line arguments parser
    @property
    def argparser(self):
        if self.protocol is None:
            steps = "\n".join([str(idx + 1) + "- " + step.__name__  for idx, step in enumerate(self.steps)])
        else:
            steps = ""
            for i in range(0, len(self.protocol)):
                steps += "\n----\n"+self.protocol[i]+":\n"+"\n".join([str(idx + 1) + "- " + step.__name__  for idx, step in enumerate(self.steps[i])])

        if not hasattr(self, "_argparser"):
            epilog = textwrap.dedent("""\
                Steps:
                ------
                {steps}
            """).format(steps=steps)

            # Create ArgumentParser with numbered step list and description as epilog
            self._argparser = argparse.ArgumentParser(
                    formatter_class=argparse.RawDescriptionHelpFormatter,
                    epilog=epilog,
                    conflict_handler='resolve')

            # Common options for all pipelines
            self._argparser.add_argument("--help", help="show detailed description of pipeline and steps", action="store_true")
            self._argparser.add_argument("-c", "--config", help="config INI-style list of files; config parameters are overwritten based on files order", nargs="+", type=file)
            self._argparser.add_argument("-s", "--steps", help="step range e.g. '1-5', '3,6,7', '2,4-8'")
            self._argparser.add_argument("-o", "--output-dir", help="output directory (default: current)", default=os.getcwd())
            self._argparser.add_argument("-j", "--job-scheduler", help="job scheduler type (default: pbs)", choices=["pbs", "batch", "daemon", "slurm"], default="slurm")
            self._argparser.add_argument("-f", "--force", help="force creation of jobs even if up to date (default: false)", action="store_true")
            self._argparser.add_argument("--json", help="create a JSON file per analysed sample to track the analysis status (default: false)", action="store_true")
            self._argparser.add_argument("--report", help="create 'pandoc' command to merge all job markdown report files in the given step range into HTML, if they exist; if --report is set, --job-scheduler, --force, --clean options and job up-to-date status are ignored (default: false)", action="store_true")
            self._argparser.add_argument("--clean", help="create 'rm' commands for all job removable files in the given step range, if they exist; if --clean is set, --job-scheduler, --force options and job up-to-date status are ignored (default: false)", action="store_true")
            self._argparser.add_argument("-l", "--log", help="log level (default: info)", choices=["debug", "info", "warning", "error", "critical"], default="info")

        return self._argparser

    # Pipeline command line arguments
    @property
    def args(self):
        return self._args

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def output_dir(self):
        return self._output_dir

    @property
    def report_template_dir(self):
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))), "bfx", "report")

    @property
    def scheduler(self):
        return self._scheduler

    @property
    def force_jobs(self):
        return self._force_jobs

    @property
    def protocol(self):
        return self._protocol

    @property
    def steps(self):
        # Needs to be defined in pipeline child class
        raise NotImplementedError

    @property
    def step_list(self):
        return self._step_list

    @property
    def step_range(self):
        return self._step_range
    
    @property
    def step_range_num(self):
        return self._step_range_num

    @property
    def sample_list(self):
        return self._sample_list

    @property
    def sample_paths(self):
        return self._sample_paths

    @property
    def jobs(self):
        jobs = []
        for step in self.step_range:
            jobs.extend(step.jobs)
        return jobs

    # Given a list of lists of input files, return the first valid list of input files which can be found either in previous jobs output files or on file system.
    # Thus, a job with several candidate lists of input files can find out the first valid one.
    def select_input_files(self, candidate_input_files):
        log.debug("candidate_input_files: \n" + str(candidate_input_files))

        selected_input_files = []

        # Create a reversed copy to pop the candidates ordered by priority
        remaining_candidate_input_files = list(candidate_input_files)
        remaining_candidate_input_files.reverse()
        previous_jobs_output_files = set([output_file for job in self.jobs for output_file in job.output_files])

        while not selected_input_files and remaining_candidate_input_files:
            input_files = filter(None, remaining_candidate_input_files.pop())
            # Skip empty candidate input files
            if input_files:
                # dependency_jobs() checks if the current candidate input files is valid, otherwise raises an exception
                try:
                    job = Job(input_files=input_files)
                    job.output_dir = self.output_dir
                    self.dependency_jobs(job)
                    selected_input_files = input_files
                except Exception as e:
                    log.debug("Caught Exception for candidate input file: " +  ", ".join(input_files))
                    log.debug(e.message)

        if selected_input_files:
            log.debug("selected_input_files: " + ", ".join(input_files) + "\n")
            return selected_input_files
        else:
            raise Exception("Error: missing candidate input files: " + str(candidate_input_files) +
                " neither found in dependencies nor on file system!")

    def dependency_jobs(self, current_job):
        dependency_jobs = []
        dependency_input_files = set()
        for step in self.step_range:
            for step_job in step.jobs:
                # If current job input files intersect with step job output files, step job is a dependency
                shared_files = set(current_job.input_files).intersection(set(step_job.output_files))
                if shared_files:
                    dependency_jobs.append(step_job)
                    dependency_input_files.update(shared_files)

        # Check if job input files not found in dependencies are on file system
        missing_input_files = set()
        # Add current_job.output_files in case of "... && ..." command
        # where first command output becomes second command input
        for remaining_input_file in set(current_job.input_files).difference(dependency_input_files).difference(set(current_job.output_files)):
            # Use 'exists' instead of 'isfile' since input file can be a directory
            if not os.path.exists(current_job.abspath(remaining_input_file)):
                missing_input_files.add(remaining_input_file)
        if missing_input_files:
            raise Exception("Error: missing input files for job " + current_job.name + ": " +
                ", ".join(missing_input_files) + " neither found in dependencies nor on file system!")

        return dependency_jobs

    def create_jobs(self):
        # the flowchart creation engine is called from here as the pipeline
        # itself is created.  Get name of pipeline and use the corresponding
        # hierarchy file.  Can be made better in the real implementation.
        # Another assumption is both fatq and bam files are available.  The
        # focus right now is to create a minimal working example.
        if str(type(self)).split('.')[-1].strip('\'>') == 'DnaSeq':
            FlowChart(
                steps=self.step_range_num,
                fname=os.path.dirname(os.path.realpath(__file__))+'/hierarchies/hierarchy_dnaseq.tsv',
                name=self.args.steps, if_bam=True, if_fastq=True)

        for step in self.step_range:
            log.info("Create jobs for step " + step.name + "...")
            jobs = step.create_jobs()
            for job in jobs:
                # Job name is mandatory to create job .done file name
                if not job.name:
                    raise Exception("Error: job \"" + job.command + "\" has no name!")

                log.debug("Job name: " + job.name)
                log.debug("Job input files:\n  " + "\n  ".join(job.input_files))
                log.debug("Job output files:\n  " + "\n  ".join(job.output_files) + "\n")

                # Job .done file name contains the command checksum.
                # Thus, if the command is modified, the job is not up-to-date anymore.
                job.done = os.path.join("job_output", step.name, job.name + "." + hashlib.md5(job.command_with_modules).hexdigest() + ".mugqic.done")
                job.output_dir = self.output_dir
                job.dependency_jobs = self.dependency_jobs(job)

                if not self.force_jobs and job.is_up2date():
                    log.info("Job " + job.name + " up to date... skipping")
                else:
                    step.add_job(job)
                    if job.samples:
                        for sample in job.samples:
                            if sample not in self.sample_list:
                                self.sample_list.append(sample)

            log.info("Step " + step.name + ": " + str(len(step.jobs)) + " job" + ("s" if len(step.jobs) > 1 else "") + " created" + ("" if step.jobs else "... skipping") + "\n")

        # Now create the json dumps for all the samples if not already done
        if self.args.json:
            for sample in self.sample_list:
                self.sample_paths.append(jsonator.create(self, sample))

        log.info("TOTAL: " + str(len(self.jobs)) + " job" + ("s" if len(self.jobs) > 1 else "") + " created" + ("" if self.jobs else "... skipping") + "\n")

    def submit_jobs(self):
        self.scheduler.submit(self)

        # Print a copy of sample JSONs for the genpipes dashboard
        portal_output_dir = config.param('DEFAULT', 'portal_output_dir', required=False)
        if self.args.json and portal_output_dir != "":
            if not os.path.isdir(os.path.expandvars(portal_output_dir)):
                raise Exception("Directory path \"" + portal_output_dir + "\" does not exist or is not a valid directory!")
            copy_commands = []
            for i, sample in enumerate(self.sample_list):
                input_file = self.sample_paths[i]
                output_file = os.path.join(portal_output_dir, '$USER.' + sample.name + '.' + uuid4().get_hex() + '.json')
                copy_commands.append("cp \"{input_file}\" \"{output_file}\"".format(
                    input_file=input_file, output_file=output_file))

            print(textwrap.dedent("""
                #------------------------------------------------------------------------------
                # Print a copy of sample JSONs for the genpipes dashboard
                #------------------------------------------------------------------------------
                {copy_commands}
            """).format(copy_commands='\n'.join(copy_commands)))


    def report_jobs(self, output_dir=None):
        if not output_dir:
            output_dir = self.output_dir  # Default to pipeline output directory
        report_files = []
        for job in self.jobs:
            # Retrieve absolute paths of report files
            for report_file in job.report_files:
                if report_file not in report_files:
                    if os.path.exists(os.path.join(output_dir, report_file)) :
                        report_files.append(report_file)
                    else:
                        log.warn("Report file: " + report_file + " not found!... skipping")
        if report_files:
            # Copy images and other HTML dependencies into report directory
            # Print pandoc command with all markdown report files and config/references sections at the end
            print("""\
#!/bin/bash
# Exit immediately on error
set -eu -o pipefail

module load {module_pandoc}
cd {output_dir}
mkdir -p report
cp -r \\
  {self.report_template_dir}/css/ \\
  {self.report_template_dir}/images/ \\
  {self.report_template_dir}/_js/ \\
  {self.report_template_dir}/config_and_references.md \\
  report/
cp {config_file} report/config.ini
pandoc \\
  --toc \\
  --toc-depth=6 \\
  --template={self.report_template_dir}/template.html \\
  --css=css/style.css \\
  --variable title="{title}" \\
  --filter pandoc-citeproc \\
  <(pandoc --to=markdown \\
    --template {introduction} \\
    --variable date="{date}" \\
    {introduction} \\
  ) \\
  {report_files} \\
  report/config_and_references.md \\
  --output report/index.html""".format(
                module_pandoc=config.param('report', 'module_pandoc'),
                output_dir=output_dir,
                config_file=config.filepath,
                self=self,
                title=config.param('report', 'title'),
                introduction=os.path.join(self.report_template_dir, self.__class__.__name__ + '.introduction.md'),
                date=datetime.datetime.now().strftime("%Y-%m-%d"),
                report_files=" \\\n  ".join(report_files)
            ))

    def clean_jobs(self):
        abspath_removable_files = []
        for job in self.jobs:
            # Retrieve absolute paths of removable files
            abspath_removable_files.extend([job.abspath(removable_file) for removable_file in job.removable_files])
        # Remove removable file duplicates but keep the order
        for removable_file in list(collections.OrderedDict.fromkeys(abspath_removable_files)):
            if os.path.exists(removable_file):
                print("rm -rf " + removable_file)


# Return a range list given a string.
# e.g. parse_range('1,3,5-12') returns [1, 3, 5, 6, 7, 8, 9, 10, 11, 12]
def parse_range(astr):
    result = set()
    for part in astr.split(','):
        x = part.split('-')
        result.update(range(int(x[0]), int(x[-1]) + 1))
    return sorted(result)



class FlowChart():
    """
    This FlowChart class helps create user-friendly flow charts when a
    pipeline is executed (either in its entirety or partially). This script
    needs the user to select steps that are linked to each other; in other
    words, a step can not be executed unless its predecessor is executed.

    Requirements:

    - a hierarchy file, specifying the predecessor(s) for each node. The
    format for the hierarchy file is specified in the sample hierarchy file.

    - steps, specified in the execution of the pipeline.

    """

    def __init__(self, steps=[], hierarchy_file_name='', name='all', if_bam=True, if_fastq=True):
        """
        Parameters
        ----------
        steps: list
            Steps of the pipeline being run
        hierarchy_file_name: string
            Path to hierarchy_file
        if_bam: boolean
            Stores if READSET has BAM data or not
        if_fastq: boolean
            Stores if READSET has FASTQ data or not

        Modifies
        ----------
        self.if_bam: boolean
            Stores if READSET has BAM data or not
        self.if_fastq: boolean
            Stores if READSET has FASTQ data or not
        self.step_list: list
            Stores list of steps
        """

        self.if_bam = if_bam
        self.if_fastq = if_fastq
        self.step_list = [str(i) for i in steps]
        self.steps=name

        self.parse_hierarchy(hierarchy_file_name)
        self.create_flowchart(self.check_validity())

        
    def parse_hierarchy(self, hierarchy_file_name):
        """
        This function parses the hierarchy file in order to identify the
        relation between nodes.

        Parameters
        ----------
        hierarchy_file_name: path
            Name of file containing the relations between nodes

        Modifies
        ----------
        self.links: dict
            Dictionary of links between steps
        self.name_list: list
            List of names of steps
        self.hierarchy_file: string
            Stores the path to the hierarchy_file
        self.max_step: int
            Stores the id of the final step in the pipeline
        """

        self.links = dict()
        self.name_list = []
        self.hierarchy_file = hierarchy_file_name
        self.hierarchy_file_name = hierarchy_file_name.split('/')[-1]
        self.max_step = 1

        with open(hierarchy_file_name, "r") as f:
            for line in f:

                # ignoring commented lines
                if line[0] != "#":

                    # replacing multiple intercolumnar tabs by a single tab
                    line = "\t".join(line.split())
                    splitted = line.split("\t")

                    predecessor_term = splitted[0]
                    step_term = splitted[1]
                    step_number = step_term.split(":")[0]
                    step_name = step_term.split(":")[1]
                    self.name_list.append(step_name)
                    self.links[step_number] = predecessor_term

                    # identify the final step
                    if int(step_number) > self.max_step:
                        self.max_step = int(step_number)

                        
    def check_validity(self):
        """
        This function checks if the steps inputted are continuous or not. The
        flowchart is created only if the steps are interconnected.

        Parameters
        ----------

        Modifies
        ----------

        """
        # make a copy of the list of steps
        temp_list = self.step_list[:]

        # add BAM/FASTQ to the copy of list of steps to account for top nodes
        if self.if_bam:
            temp_list.append("BAM")
        if self.if_fastq:
            temp_list.append("FASTQ")

        for step in temp_list:
            # ignore the validation for dummy values BAM and FASTQ
            if step == "BAM" or step == "FASTQ":
                continue

            # pred = predecessor(s) of step
            pprint(self.links)
            pred = self.links[step]

            # if step has only one predecessor
            if "," not in pred and "+" not in pred:
                if pred not in temp_list:
                    return False

            else:
                # if pred has multiple predecessors
                separator_list = [",", "+"]
                for separator in separator_list:
                    if separator in pred:
                        pred_list = pred.strip().split(separator)

                        # initialize flag to false, set flag to true if any
                        # one of the mandated predecessors exists in the list
                        flag = False
                        for item in pred_list:
                            if item in temp_list:
                                flag = True

                        if not flag:
                            return False

        return True

    
    def create_flowchart(self, verity):
        """
        This function uses the consecution module and builds a flowchart of
        the steps involved in the process.

        Parameters
        ----------
        verity: boolean
            Indicates whether a connected pipeline can be made or not

        Modifies
        ----------

        """

        # if graph is erroneous, create dummy file and exit
        if not verity:

            # create a graph using Graphviz
            dot = Digraph(comment="Flowchart",
                          node_attr={"shape": "plaintext"})

            # add error node
            dot.node("0", "Graph not created: some nodes don't have a source")

            try:
                # create folder if not exists
                dir_name = "flowcharts/"
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name)

                if self.if_bam and self.if_fastq:
                    dot.render(dir_name + self.hierarchy_file_name + "-" +
                               self.steps + ".bam.fastq.error")

                if self.if_bam and not self.if_fastq:
                    dot.render(dir_name + self.hierarchy_file_name + "-" +
                               self.steps + ".bam.error")

                if not self.if_bam and self.if_fastq:
                    dot.render(dir_name + self.hierarchy_file_name + "-" +
                               self.steps + ".fastq.error")

                print("Error: some nodes don't have a source.")

            except Exception as inst:

                # raise exception if file is open and can not be modified
                print("The target file seems to be open already. Please" +
                      " close the file before proceeding.")

            return

        # store all the nodes that have been added so far
        added_nodes = []

        # store all the edges that have been added so far
        added_tuples = []

        # creating a copy of self.step_list with BAM/FASTQ in it
        temp_list = self.step_list[:]

        # hard code the BAM, FASTQ node if present
        if self.if_bam:
            added_nodes.append("BAM")
            temp_list.append("BAM")
        if self.if_fastq:
            added_nodes.append("FASTQ")
            temp_list.append("FASTQ")

        for step in temp_list:
            if step == "BAM" or step == "FASTQ":
                continue

            # if step has only one predecessor
            if "," not in self.links[step] and "+" not in self.links[step]:

                # if step is not added, add a node for step
                if step not in added_nodes:
                    added_nodes.append(step)

                # if link[step] is not added, add a node for link[step]
                if self.links[step] not in added_nodes:
                    added_nodes.append(self.links[step])

                added_tuples.append((self.links[step], step))

            # if step has multiple predecessors of which one has to be chosen
            if "," in self.links[step]:

                # if step is not added, add a node for step
                if step not in added_nodes:
                    added_nodes.append(step)

                pred_list = self.links[step].strip().split(",")
                for item in pred_list:

                    # if there actually exists a link between this predecessor
                    # and step, proceed
                    if item in temp_list:

                        added_tuples.append((item, step))

                        # if item is not added, add a node for item
                        if item not in added_nodes:
                            added_nodes.append(item)

                        # since only one link needs to considered, break
                        break

            # if step has multiple predecessors of which all can chosen
            if "+" in self.links[step]:

                # if step is not added, add a node for step
                if step not in added_nodes:
                    added_nodes.append(step)

                pred_list = self.links[step].strip().split("+")
                for item in pred_list:

                    # if there actually exists a link between this predecessor
                    # and step, proceed
                    if item in temp_list:

                        added_tuples.append((item, step))

                        # if item is not added, add a node for item
                        if item not in added_nodes:
                            added_nodes.append(item)

        # create a graph using Graphviz
        dot = Digraph(comment="Flowchart", node_attr={"shape": "rectangle"})

        # add nodes
        for i in added_nodes:
            if i == "BAM":
                dot.node(i, "BAM")
            if i == "FASTQ":
                dot.node(i, "FASTQ")
            if i != "BAM" and i != "FASTQ":
                dot.node(i, i + ":" + self.name_list[int(i) - 1])

        # add edges
        for (i, j) in added_tuples:
            dot.edge(i, j)

        dot.edge_attr.update(arrowhead="normal")

        try:
            # create folder if not exists
            dir_name = "flowcharts/"
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)

            # save graph
            if self.if_bam and self.if_fastq:
                dot.render(dir_name + self.hierarchy_file_name + "-" + self.steps +
                           ".bam.fastq.flow")

            if self.if_bam and not self.if_fastq:
                dot.render(dir_name + self.hierarchy_file_name + "-" + self.steps +
                           ".bam.flow")

            if not self.if_bam and self.if_fastq:
                dot.render(dir_name + self.hierarchy_file_name + "-" + self.steps +
                           ".fastq.flow")

            print("Flowchart saved successfully.")

        except Exception as inst:
            # raise exception if file is open and can not be modified
            print("The target file seems to be open already. Please" +
                  " close the file before proceeding.")
