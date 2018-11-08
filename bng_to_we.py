import argparse, yaml, os, shutil
import subprocess as sbpc

# TODO: Eventually re-write so that we have a single check
# function to check everything is in place before doing anything
# and then make the actual folder. For now, let's test
class BNGL_TO_WE:
    def __init__(self):
        '''
        '''
        # read the options file
        self._parse_args()
        self.opts = self._load_yaml(self.args.opts)
        self.main_dir = os.getcwd()

    def _parse_args(self):
        '''
        '''
        parser = argparse.ArgumentParser()

        # Data input options
        parser.add_argument('--options', '-opts',
                            dest='opts',
                            required=True,
                            help='Options YAML file, required',
                            type=str)

        self.args = parser.parse_args()

    def _load_yaml(self, yfile):
        f = open(yfile, "r")
        y = yaml.load(f)
        f.close()
        return y

    def _write_runsh(self):
        lines = [
          '#!/bin/bash\n',
          'source env.sh\n',
          '$WEST_ROOT/bin/w_run --work-manager processes "$@"\n'\
          ]

        f = open("run.sh", "w")
        f.writelines(lines)
        f.close()

    def _write_envsh(self):
        lines = [
            '#!/bin/sh\n',
            'export WEST_SIM_ROOT="$PWD"\n',
            'export RunNet="$WEST_SIM_ROOT/bngl_conf/run_network"\n',
            'export SIM_NAME=$(basename $WEST_SIM_ROOT)\n'
            ]

        f = open("env.sh", "w")
        f.writelines(lines)
        f.close()

    def _write_auxfuncs(self):
        lines = [
              '#!/usr/bin/env python\n',
              'import numpy\n',
              'def pcoord_loader(fieldname, coord_filename, segment, single_point=False):\n',
              '    pcoord    = numpy.loadtxt(coord_filename, dtype = numpy.float32)\n',
              '    if not single_point:\n',
              '        segment.pcoord = pcoord[:,1:]\n',
              '    else:\n',
              '        segment.pcoord = pcoord[1:]'
              ]

        f = open("aux_functions.py", "w")
        f.writelines(lines)
        f.close()

    def _write_bstatestxt(self):
        lines = [
            '0 1 0.net'
          ]

        f = open("bstates/bstates.txt", "w")
        f.writelines(lines)
        f.close()

    def _write_getpcoord(self):
        lines = [
            '#!/bin/bash\n',
            'if [ -n "$SEG_DEBUG" ] ; then\n',
            '  set -x\n',
            '  env | sort\n',
            'fi\n',
            'cd $WEST_SIM_ROOT\n',
            'cat bngl_conf/init.gdat > $WEST_PCOORD_RETURN\n',
            'if [ -n "$SEG_DEBUG" ] ; then\n',
            '  head -v $WEST_PCOORD_RETURN\n',
            'fi\n'
            ]

        f = open("westpa_scripts/get_pcoord.sh", "w")
        f.writelines(lines)
        f.close()

    def _write_postiter(self):
        lines = [
            '#!/bin/bash\n',
            'if [ -n "$SEG_DEBUG" ] ; then\n',
            '    set -x\n',
            '    env | sort\n',
            'fi\n',
            'cd $WEST_SIM_ROOT || exit 1\n',
            'if [[ $WEST_CURRENT_ITER -gt 3 ]];then\n',
            '  PREV_ITER=$(printf "%06d" $((WEST_CURRENT_ITER-3)))\n',
            '  rm -rf ${WEST_SIM_ROOT}/traj_segs/${PREV_ITER}\n',
            '  rm -f  seg_logs/${PREV_ITER}-*.log\n',
            'fi\n'
            ]

        f = open("westpa_scripts/post_iter.sh", "w")
        f.writelines(lines)
        f.close()

    def write_dynamic_files(self):
        self._write_initsh()
        self._write_systempy()
        self._write_westcfg()
        self._write_runsegsh()

    def write_static_files(self):
        # everything here assumes we are in the right folder
        self._write_runsh()
        self._write_envsh()
        self._write_auxfuncs()
        self._write_bstatestxt()
        self._write_getpcoord()
        self._write_postiter()

    def make_sim_folders(self):
        '''
        '''
        fname = self.opts.get("sim_name", "WE_BNG_sim")
        self.sim_dir = fname
        os.makedirs(fname)
        os.chdir(fname)
        os.makedirs("bngl_conf")
        os.makedirs("bstates")
        os.makedirs("westpa_scripts")


    def copy_run_network(self):
        # Assumes path is absolute path and not relative
        bng_path = self.opts.get("bng_path", None)
        if bng_path is None: 
            sys.exit("bng_path is not specified in the options file")
        shutil.copyfile(os.path.join(bng_path, "bin/run_network"), "bngl_conf/run_network")

    def run_BNGL_on_file(self):
        bng_path = self.opts.get("bng_path", None)
        if bng_path is None:
            sys.exit("bng_path is not specified in the options file")
        bngpl = os.path.join(bng_path, "BNG2.pl")
        # IMPORTANT! 
        # This assumes that the bngl file doesn't have any directives at the end! 
        bngl_file = self.opts.get("bngl_file", None)
        if bngl_file is None:
            sys.exit("bngl_file path is not specified in the options file")
        # we have a bngl file
        os.chdir("bngl_conf")
        # Get into a folder specifically for this purpose
        os.mkdir("BNGL")
        os.chdir("BNGL")
        # Make specific BNGL files for a) generating network and then 
        # b) getting a starting  gdat file
        shutil.copyfile(bngl_file, "for_network.bngl")
        f = open("for_network.bngl", "a")
        # Adding directives to generate the files we want
        f.write('generate_network({overwrite=>1});\n')
        f.close()
        shutil.copyfile(bngl_file, "for_gdat.bngl")
        f = open("for_gdat.bngl", "a")
        # Adding directives to generate the files we want
        f.write('generate_network({overwrite=>1});\n')
        f.write('simulate({method=>"ssa",t_end=>2,n_steps=>1});\n')
        f.close()
        # run BNG2.pl on things to get the files we need
        proc = sbpc.Popen([bngpl, "for_network.bngl"])
        proc.wait()
        assert proc.returncode == 0, "call to BNG2.pl failed, make sure it's in your PATH"
        # copy our network back
        shutil.copyfile("for_network.net", "../init.net")
        # run on gdat 
        proc = sbpc.Popen([bngpl, "for_gdat.bngl"])
        proc.wait()
        assert proc.returncode == 0, "call to BNG2.pl failed, make sure it's in your PATH"
        # edit the gdat file to get rid of the last line
        f = open("for_gdat.gdat", "r")
        l = f.readlines()
        f.close()
        # Now write the first two lines to init.gdat
        f = open("../init.gdat", "w")
        f.writelines(l[:2])
        f.close()
        # return to main simulation folder
        os.chdir(os.path.join(self.main_dir, self.sim_dir))

    def run(self):
        '''
        '''
        self.make_sim_folders()
        self.copy_run_network()
        self.write_static_files()
        self.run_BNGL_on_file()
        self.write_dynamic_files()
        return

if __name__ == "__main__":
    btw = BNGL_TO_WE()
    btw.run()
