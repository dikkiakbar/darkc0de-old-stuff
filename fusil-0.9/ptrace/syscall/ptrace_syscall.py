from os import strerror
from itertools import izip
from ptrace.cpu_info import CPU_X86_64, CPU_PPC, CPU_I386
from ptrace.ctypes_tools import ulong2long, formatAddress, formatWordHex
from ptrace.func_call import FunctionCall
from ptrace.syscall import SYSCALL_NAMES, SYSCALL_PROTOTYPES, SyscallArgument
from ptrace.syscall.socketcall_call import setupSocketCall
from ptrace.os_tools import RUNNING_LINUX, RUNNING_BSD
from ptrace.cpu_info import CPU_WORD_SIZE

class PtraceSyscall(FunctionCall):
    def __init__(self, process, options):
        FunctionCall.__init__(self, "syscall", options, SyscallArgument)
        self.process = process
        self.restype = "long"
        regs = process.getregs()
        self.readSyscall(regs)
        argument_values = self.readArgumentValues(regs)
        self.readArguments(argument_values)
        self.enter()

    def enter(self):
        if self.name == "socketcall" and self.options.replace_socketcall:
            setupSocketCall(self, self.process, self[0], self[1].value)

        # Format arguments before syscall exit
        if self.name == "select":
            for argument in self.arguments[1:4]:
                # Read argument content of arguments 2, 3 and 4
                argument.format()
        elif self.name in ("execve", "clone"):
            # Pre-format all arguments
            for argument in self.arguments:
                argument.format()

    def readSyscall(self, regs):
        # Read syscall number
        if CPU_PPC:
            self.syscall = regs.gpr0
        elif RUNNING_LINUX:
            if CPU_X86_64:
                self.syscall = regs.orig_rax
            else:
                self.syscall = regs.orig_eax
        else:
            self.syscall = regs.eax

        # Get syscall variables
        self.name = SYSCALL_NAMES.get(self.syscall, "syscall<%s>" % self.syscall)

    def readArgumentValues(self, regs):
        if RUNNING_BSD:
            sp = self.process.getStackPointer()
            return [ self.process.readWord(sp + index*CPU_WORD_SIZE)
                for index in xrange(1, 6+1) ]
        if CPU_I386:
            return (regs.ebx, regs.ecx, regs.edx, regs.esi, regs.edi, regs.ebp)
        if CPU_X86_64:
            return (regs.rdi, regs.rsi, regs.rdx, regs.r10, regs.r8, regs.r9)
        if CPU_PPC:
            return (regs.gpr3, regs.gpr4, regs.gpr5, regs.gpr6, regs.gpr7, regs.gpr8)
        raise NotImplementedError()

    def readArguments(self, argument_values):
        if self.name in SYSCALL_PROTOTYPES:
            self.restype, formats = SYSCALL_PROTOTYPES[self.name]
            for value, format in izip(argument_values, formats):
                argtype, argname = format
                self.addArgument(value=value, name=argname, type=argtype)
        else:
            for value in argument_values:
                self.addArgument(value=value)

    def formatExit(self, process):
        if CPU_I386:
            regname = "eax"
        elif CPU_X86_64:
            regname = "rax"
        elif CPU_PPC:
            regname = "result"
        else:
            raise NotImplementedError()
        self.result = process.getreg(regname)

        if self.restype.endswith("*"):
            text = formatAddress(self.result)
        else:
            uresult = self.result
            self.result = ulong2long(self.result)
            if self.result < 0:
                text = "%s (%s)" % (
                    self.result, strerror(-self.result))
            elif not(0 <= self.result <= 9):
                text = "%s (%s)" % (self.result, formatWordHex(uresult))
            else:
                text = str(self.result)
        return text

    def __str__(self):
        return "<Syscall name=%r>" % self.name

