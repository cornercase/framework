#!/opt/gpi/bin/python

#    Copyright (C) 2014  Dignity Health
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    NO CLINICAL USE.  THE SOFTWARE IS NOT INTENDED FOR COMMERCIAL PURPOSES
#    AND SHOULD BE USED ONLY FOR NON-COMMERCIAL RESEARCH PURPOSES.  THE
#    SOFTWARE MAY NOT IN ANY EVENT BE USED FOR ANY CLINICAL OR DIAGNOSTIC
#    PURPOSES.  YOU ACKNOWLEDGE AND AGREE THAT THE SOFTWARE IS NOT INTENDED FOR
#    USE IN ANY HIGH RISK OR STRICT LIABILITY ACTIVITY, INCLUDING BUT NOT
#    LIMITED TO LIFE SUPPORT OR EMERGENCY MEDICAL OPERATIONS OR USES.  LICENSOR
#    MAKES NO WARRANTY AND HAS NOR LIABILITY ARISING FROM ANY USE OF THE
#    SOFTWARE IN ANY HIGH RISK OR STRICT LIABILITY ACTIVITIES.

# Brief: a make script that can double as a setup script.
 
'''
A C/C++ extension module that implements an alorithm or method.

    To make, issue the following command:
        $ ./make.py <basename>
        or
        $ ./make.py <basename>.cpp
        or
        $ ./make.py <basename>.py
'''
from distutils.core import setup, Extension
import os
import sys
import optparse  # get and process user input args
import platform
import py_compile
import traceback

GPI_PKG='/opt/gpi/'
GPI_INC=GPI_PKG+'include/'
GPI_FRAMEWORK=GPI_PKG+'lib/'
GPI_BIN=GPI_PKG+'bin/'
GPI_THIRD=GPI_PKG+'local/'
sys.path.insert(0, GPI_FRAMEWORK)

# gpi
from gpi.config import Config

print("\n"+str(sys.version)+"\n")

# from:
# http://stackoverflow.com/questions/287871/print-in-terminal-with-colors-using-python
class Cl:
    HDR = '\033[95m'
    OKBL = '\033[94m'
    OKGR = '\033[92m'
    WRN = '\033[93m'
    FAIL = '\033[91m'
    ESC = '\033[0m'

# add the macports path for local utils
if platform.system() == 'Darwin':  # OSX
    os.environ['PATH'] += ':'+GPI_THIRD+'/macports/bin'

# The basic distutils setup().
def compile(mod_name, include_dirs=[], libraries=[], library_dirs=[],
            extra_compile_args=[], runtime_library_dirs=[]):

    print "Making target: " + mod_name

    # do usual generic module setup
    # NOT: 'mod_name' must have an init<name>
    # function defined in the .cpp code.
    Module1 = Extension(mod_name,
                        # define_macros = [('MAJOR_VERSION',
                        # '1'),('MINOR_VERSION', '0')],
                        include_dirs=list(set(include_dirs)),
                        libraries=list(set(libraries)),
                        library_dirs=list(set(library_dirs)),
                        extra_compile_args=list(set(extra_compile_args)),
                        runtime_library_dirs=list(set(runtime_library_dirs)),
                        sources=[mod_name + '_PyMOD.cpp'])

    # run the setup() function
    try:
        setup(name=mod_name,
              version='0.1-dev',
              description='A kcii library of algorithms and methods.',
              ext_modules=[Module1],
              script_args=["build_ext", "--inplace", "--force"])
    except:
        print sys.exc_info()
        print "FAILED: " + mod_name
        return 1

    print "SUCCESS: " + mod_name
    return 0


def packageArgs(args):
    """Split path and filename info into a dictionary.
    """
    cwd = os.getcwd()
    targets = []
    for arg in args:
        fn = os.path.splitext(os.path.basename(arg))[0]
        ext = os.path.splitext(os.path.basename(arg))[1]
        dn = os.path.dirname(arg)
        targets.append({'pth': cwd + '/' + dn, 'fn': fn, 'ext': ext})
    return targets

def isPythonPackageDir(path):
    return os.path.isfile(str(path)+'/__init__.py')

def findLibraries(basepath):
    # TODO: this searching should be combined with the search in library.py and
    # unified in config.py since they both need to know which libraries are
    # present.

    # if the basepath IS the library directory
    if isPythonPackageDir(basepath):
        return [basepath]

    # check for subdirectories
    libs = []
    for p in os.listdir(basepath):
        subdir = os.path.join(basepath,p)
        if os.path.isdir(subdir):
            if isPythonPackageDir(subdir):
                libs.append(subdir)
    return libs

def targetWalk(recursion_depth=1):
    """Recurse into directories and look for .cpp files to compile.
    TODO: check if the file is a valid python module.
    """
    targets = []
    ipath = os.getcwd()
    ocnt = ipath.count('/')
    for path, dn, fn in os.walk(ipath):
        if path.count('/') - ocnt <= recursion_depth:
            if len(fn):
                for fil in fn:

                    # only attempt _PyMOD.cpp
                    if fil.endswith(".cpp"):
                        if fil.endswith("_PyMOD.cpp"):
                            fn = os.path.splitext(fil)[0]
                            ext = os.path.splitext(fil)[1]
                            targets.append({'pth': path, 'fn': fn, 'ext': ext})

                    # byte-compile all .py files
                    if fil.endswith(".py"):
                        fn = os.path.splitext(fil)[0]
                        ext = os.path.splitext(fil)[1]
                        targets.append({'pth': path, 'fn': fn, 'ext': ext})

    return targets


def makePy(basename, ext, fmt=False):

    target = [basename, ext]

    # AUTOPEP8
    if fmt:
        try:
            import autopep8
            print "\nFound: autopep8 " + str(autopep8.__version__) + "..."
            print "Reformatting Python script: " + "".join(target)
            os.system('autopep8 -i ' + "".join(target))
        except:
            print "Failed to perform auto-formatting \
                with \'autopep8\'."

    # PEP8
    try:
        import pep8
        print "\nFound: pep8 " + str(pep8.__version__) + "..."
        print "Checking Python script: " + "".join(target)
        print "pep8 found these problems with your code, START" + Cl.WRN
        os.system('pep8 --count --statistics --show-source '
                  + "".join(target))
        print Cl.ESC + "pep8 END"
    except:
        print "Failed to perform check with \'pep8\'."

    # PYFLAKES
    try:
        import pyflakes
        print "\nFound: pyflakes " + str(pyflakes.__version__) + "..."
        print "Checking Python script: " + "".join(target)
        print "pyflakes found these problems with your code, START" + Cl.FAIL
        os.system('pyflakes ' + "".join(target))
        print Cl.ESC + "pyflakes END"
    except:
        print "Failed to perform check with \'pyflakes\'."

    # FORCE COMPILE
    try:
        print '\nAttemping py_compile...'
        py_compile.compile(''.join(target), doraise=True)
        print 'py_compile END'
        print '\nSUCCESS: '+''.join(target)
        return 0
    except:
        print Cl.FAIL + str(traceback.format_exc()) + Cl.ESC
        print 'py_compile END'
        print '\nFAILED: '+''.join(target)
        return 1


if __name__ == '__main__':

    parser = optparse.OptionParser()
    parser.add_option('--preprocess', dest='preprocess', default=False,
                      action="store_true", help='''Only do preprocessing to \
                              target (the resulting .o file will be \
                              preprocessed code.)''')
    parser.add_option('-w', '--suppressWarnings', dest='suppressWarnings',
                      default=False, action="store_true",
                      help='''Tell gcc to only display errors.''')
    parser.add_option('--fmt', dest='format', default=False,
                      action="store_true",
                      help="Auto-format using the autopep8 and astyle scripts.")
    parser.add_option('--all', dest='makeall', default=False,
                      action='store_true',
                      help="Recursively search for .cpp files and attempt to" +
                      "make them (integer arg sets recursion depth).")
    parser.add_option('-r', '--rdepth', dest='makeall_rdepth', type="int",
                      default=1,
                      help="Integer arg sets recursion depth for makeall.")
    parser.add_option('--debug', dest='debug', default=False,
                      action='store_true',
                      help="Uses range checker for PyFI::Array calls.")

    parser.add_option(
        '-v', '--verbose', dest='verbose', default=False, action="store_true",
        help='''Verbosity.''')

    parser.add_option(
        '-d', '--distdebug', dest='distdebug', default=False, action="store_true",
        help='''Sets DISTUTILS_DEBUG. ''')

    # get user input 'options', and extra 'args' that were unprocessed
    options, args = parser.parse_args()
    opt = vars(options)

    # debug the distutils setup()
    if options.distdebug:
        os.environ['DISTUTILS_DEBUG'] = '1'

    # gather args and their path info
    targets = None
    if len(args):
        targets = packageArgs(args)

    # gather all _PyMOD.cpp and .py files
    # supersedes 'args' if present.
    if options.makeall:
        if options.makeall_rdepth < 0:
            print Cl.FAIL + "ERROR: recursion depth is set to an invalid number." + Cl.ESC
            sys.exit(-1)
        targets = targetWalk(options.makeall_rdepth)

    if targets is None:
        print Cl.FAIL + "ERROR: no targets specified." + Cl.ESC
        sys.exit(-1)

    # LIBRARIES, INCLUDES, ENV-VARS
    include_dirs = [GPI_INC]
    libraries = []
    library_dirs = []
    extra_compile_args = []  # ['--version']
    runtime_library_dirs = []

    # USER MAKE config
    if (len(Config.MAKE_CFLAGS) + len(Config.MAKE_LIBS) + len(Config.MAKE_INC_DIRS) + len(Config.MAKE_LIB_DIRS)) > 0:
        print "Adding USER include dirs"
        # add user libs
        libraries += Config.MAKE_LIBS
        include_dirs += Config.MAKE_INC_DIRS
        library_dirs += Config.MAKE_LIB_DIRS
        extra_compile_args += Config.MAKE_CFLAGS

    # GPI library dirs
    print "Adding GPI include dirs"
    # add libs from library paths
    found_libs = {}
    for flib in Config.GPI_LIBRARY_PATH:
        if os.path.isdir(flib): # skip default config if dirs dont exist
            for usrdir in findLibraries(flib):
                p = os.path.dirname(usrdir)
                b = os.path.basename(usrdir)

                if (b in found_libs.keys()) and not (p in found_libs.values()):
                    print Cl.FAIL + "ERROR: \'" + str(b) + "\' libraray conflict:"+Cl.ESC
                    print "\t "+os.path.join(found_libs[b],b)
                    print "\t "+os.path.join(p,b)
                    sys.exit(1)

                msg = "\tGPI_LIBRARY_PATH \'"+str(p)+"\' for lib \'"+str(b)+"\'"
                include_dirs += [os.path.dirname(usrdir)]
                found_libs[b] = p
                print msg

    if len(found_libs.keys()) == 0:
        print Cl.WRN + "WARNING: No GPI libraries found!\n" + Cl.ESC

    if options.preprocess:
        extra_compile_args.append('-E')

    if options.suppressWarnings:
        extra_compile_args.append('-w')

    # debug pyfi arrays
    if options.debug:
        print "Turning on PyFI Array Debug"
        extra_compile_args += ['-DPYFI_ARRAY_DEBUG']

    # Anaconda Python/Numpy
    print "Adding Anaconda libs"
    include_dirs += [GPI_THIRD+'/anaconda/lib/python2.7/site-packages/numpy/core/include']
    include_dirs += [GPI_THIRD+'/anaconda/include']
    library_dirs += [GPI_THIRD+'/anaconda/lib']

    # POSIX THREADS
    # this location is the same for Ubuntu and OSX
    print "Adding POSIX-Threads lib"
    libraries += ['pthread']
    include_dirs += ['/usr/include']
    library_dirs += ['/usr/lib']

    # FFTW3
    print "Adding FFTW3 libs"
    libraries += ['fftw3_threads', 'fftw3', 'fftw3f_threads', 'fftw3f']
    include_dirs += [GPI_THIRD+'/fftw/include']
    library_dirs += [GPI_THIRD+'/fftw/lib']

    # The intel libs and extra compile flags are different between linux and OSX
    if platform.system() == 'Linux': 
        pass

    elif platform.system() == 'Darwin':  # OSX

        os.environ["CC"] = 'clang'
        os.environ["CXX"] = 'clang++'

        # force only x86_64
        os.environ["ARCHFLAGS"] = '-arch x86_64'

        # force 10.7 compatibility
        os.environ["MACOSX_DEPLOYMENT_TARGET"] = '10.7'

        # for malloc.h
        include_dirs += ['/usr/include/malloc']

        # default g++
        extra_compile_args += ['-Wsign-compare'] 

        # unsupported g++
        #extra_compile_args += ['-Wuninitialized']

        # warn about implicit down casting
        #extra_compile_args += ['-Wshorten-64-to-32']

    # COMPILE
    successes = []
    failures = []
    py_successes = []
    py_failures = []
    for target in targets:

        os.chdir(target['pth'])

        # PYTHON regression, error checking, pep8
        if target['ext'] == '.py':
            retcode = makePy(target['fn'], target['ext'], fmt=options.format)

            if retcode != 0:
                py_failures.append(target['fn'])
            else:
                py_successes.append(target['fn'])

        else:  # CPP compilation

            # ASTYLE
            if options.format:
                try:
                    print "\nAstyle..."
                    print "Reformatting CPP Code: " + target['fn'] + target['ext']
                    os.system(GPI_BIN+'/astyle -A1 -S -w -c -k3 -b -H -U -C '
                              + target['fn'] + target['ext'])
                    continue  # don't proceed to compile
                except:
                    print "Failed to perform auto-formatting \
                        with \'astyle\'."
                    sys.exit(-1)

            mod_name = target['fn'].split("_PyMOD")[0]
            extra_compile_args.append('-DMOD_NAME=' + mod_name)

            retcode = compile(
                mod_name, include_dirs, libraries, library_dirs,
                extra_compile_args, runtime_library_dirs)

            extra_compile_args.pop()  # remove MOD_NAME for the next target

            if retcode != 0:
                failures.append(target['fn'])
            else:
                successes.append(target['fn'])

    show_summary = len(py_successes) + len(py_failures) + len(successes) + len(failures)

    # Py Summary
    if show_summary > 1:
        print '\nSUMMARY (Py Compilations):\n\tSUCCESSES ('+Cl.OKGR+str(len(py_successes))+Cl.ESC+'):'
        for i in py_successes:
            print "\t\t" + i
        print '\tFAILURES ('+Cl.FAIL+str(len(py_failures))+Cl.ESC+'):'
        for i in py_failures:
            print "\t\t" + i

    # CPP Summary
    if show_summary > 1:
        print '\nSUMMARY (CPP Compilations):\n\tSUCCESSES ('+Cl.OKGR+str(len(successes))+Cl.ESC+'):'
        for i in successes:
            print "\t\t" + i
        print '\tFAILURES ('+Cl.FAIL+str(len(failures))+Cl.ESC+'):'
        for i in failures:
            print "\t\t" + i
