#
# This file is part of the PyMeasure package.
#
# Copyright (c) 2013-2022 PyMeasure Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import logging
from warnings import warn

import pyvisa
import numpy as np
from pkg_resources import parse_version

from pymeasure.adapters import Adapter, ProtocolAdapter

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


# noinspection PyPep8Naming,PyUnresolvedReferences
class VISAAdapter(Adapter):
    """ Adapter class for the VISA library, using PyVISA to communicate with instruments.

    The workhorse of our library, used by most instruments.

    :param resource_name: A
        `VISA resource string <https://pyvisa.readthedocs.io/en/latest/introduction/names.html>`__
        or GPIB address integer that identifies the target of the connection
    :param visa_library: PyVISA VisaLibrary Instance, path of the VISA library or VisaLibrary spec
        string (``@py`` or ``@ivi``). If not given, the default for the platform will be used.
    :param preprocess_reply: (deprecated) optional callable used to preprocess strings
        received from the instrument. The callable returns the processed string.
    :param \\**kwargs: Keyword arguments for configuring the PyVISA connection.

    :Kwargs:
        Keyword arguments are used to configure the connection created by PyVISA. This is
        complicated by the fact that *which* arguments are valid depends on the interface (e.g.
        serial, GPIB, TCPI/IP, USB) determined by the current ``resource_name``.

        A flexible process is used to easily define reasonable *default values* for
        different instrument interfaces, but also enable the instrument user to *override any
        setting* if their situation demands it.

        A kwarg that names a pyVISA interface type (most commonly ``asrl``, ``gpib``, ``tcpip`` or
        ``usb``) is a dictionary with keyword arguments defining defaults specific to that
        interface. Example: ``asrl={'baud_rate': 4200}``.

        All other kwargs are either generally valid (e.g. ``timeout=500``) or override any default
        settings from the interface-specific entries above. For example, passing
        ``baud_rate=115200`` when connecting via a resource name ``ASRL1`` would override a
        default of 4200 defined as above.

        See :ref:`connection_settings` for how to tweak settings when *connecting* to an instrument.
        See :ref:`default_connection_settings` for how to best define default settings when
        *implementing an instrument*.
    """

    def __init__(self, resource_name, visa_library='', preprocess_reply=None, **kwargs):
        super().__init__(preprocess_reply=preprocess_reply)
        if not VISAAdapter.has_supported_version():
            raise NotImplementedError("Please upgrade PyVISA to version 1.8 or later.")

        if isinstance(resource_name, ProtocolAdapter):
            self.connection = resource_name
            self.connection.write_raw = self.connection.write_bytes
            return
        elif isinstance(resource_name, VISAAdapter):
            # Allow to reuse the connection.
            self.resource_name = getattr(resource_name, "resource_name", None)
            self.connection = resource_name.connection
            return
        elif isinstance(resource_name, int):
            resource_name = "GPIB0::%d::INSTR" % resource_name
        self.resource_name = resource_name
        self.manager = pyvisa.ResourceManager(visa_library)

        # Clean up kwargs considering the interface type matching resource_name
        if_type = self.manager.resource_info(self.resource_name).interface_type
        for key in list(kwargs.keys()):  # iterate over a copy of the keys as we modify kwargs
            # Remove all interface-specific kwargs:
            if key in pyvisa.constants.InterfaceType.__members__:
                if getattr(pyvisa.constants.InterfaceType, key) is if_type:
                    # For the present interface, dump contents into kwargs first if they are not
                    # present already. This way, it is possible to override default values with
                    # kwargs passed to Instrument.__init__()
                    for k, v in kwargs[key].items():
                        kwargs.setdefault(k, v)
                del kwargs[key]

        self.connection = self.manager.open_resource(
            resource_name,
            **kwargs
        )

    @staticmethod
    def has_supported_version():
        """ Return True if the PyVISA version is greater than 1.8 """
        if hasattr(pyvisa, '__version__'):
            return parse_version(pyvisa.__version__) >= parse_version('1.8')
        else:
            return False

    def _write(self, command, **kwargs):
        """Write a string command to the instrument appending `write_termination`.

        :param str command: Command string to be sent to the instrument
            (without termination).
        :param kwargs: Keyword arguments for the connection itself.
        """
        self.connection.write(command, **kwargs)

    def _write_bytes(self, content, **kwargs):
        """Write the bytes `content` to the instrument.

        :param bytes content: The bytes to write to the instrument.
        :param kwargs: Keyword arguments for the connection itself.
        """
        self.connection.write_raw(content, **kwargs)

    def _read(self, **kwargs):
        """Read up to (excluding) `read_termination` or the whole read buffer.

        :param kwargs: Keyword arguments for the connection itself.
        :returns str: ASCII response of the instrument (excluding read_termination).
        """
        return self.connection.read(**kwargs)

    def _read_bytes(self, count, **kwargs):
        """Read a certain number of bytes from the instrument.

        :param int count: Number of bytes to read. A value of -1 indicates to
            read the whole read buffer.
        :param kwargs: Keyword arguments for the connection itself.
        :returns bytes: Bytes response of the instrument (including termination).
        """
        if count == -1:
            return self.connection.read_raw(**kwargs)
        else:
            return self.connection.read_bytes(count, **kwargs)

    def ask(self, command):
        """ Writes the command to the instrument and returns the resulting
        ASCII response

        .. deprecated:: 0.10
           Call `Instrument.ask` instead.

        :param command: SCPI command string to be sent to the instrument
        :returns: String ASCII response of the instrument
        """
        warn("Deprecated call `Instrument.ask` instead.", FutureWarning)
        return self.connection.query(command)

    def ask_values(self, command, **kwargs):
        """ Writes a command to the instrument and returns a list of formatted
        values from the result. This leverages the `query_ascii_values` method
        in PyVISA.

        .. deprecated:: 0.10
            Call `Instrument.values` instead.

        :param command: SCPI command to be sent to the instrument
        :param kwargs: Key-word arguments to pass onto `query_ascii_values`
        :returns: Formatted response of the instrument.
        """
        warn("Deprecated, call `Instrument.values` instead.", FutureWarning)

        return self.connection.query_ascii_values(command, **kwargs)

    def binary_values(self, command, header_bytes=0, dtype=np.float32):
        """ Returns a numpy array from a query for binary data

        .. deprecated:: 0.10
            Call `Instrument.binary_values` instead.

        :param command: SCPI command to be sent to the instrument
        :param header_bytes: Integer number of bytes to ignore in header
        :param dtype: The NumPy data type to format the values with
        :returns: NumPy array of values
        """
        warn("Deprecated, call `Instrument.binary_values` instead.",
             FutureWarning)
        self.connection.write(command)
        binary = self.connection.read_raw()
        # header = binary[:header_bytes]
        data = binary[header_bytes:]
        return np.fromstring(data, dtype=dtype)

    def wait_for_srq(self, timeout=25, delay=0.1):
        """ Block until a SRQ, and leave the bit high

        :param timeout: Timeout duration in seconds
        :param delay: Time delay between checking SRQ in seconds
        """
        self.connection.wait_for_srq(timeout * 1000)

    def flush_read_buffer(self):
        """ Flush and discard the input buffer

        As detailed by pyvisa, discard the read buffer contents and if data was present
        in the read buffer and no END-indicator was present, read from the device until
        encountering an END indicator (which causes loss of data).
        """
        self.connection.flush(pyvisa.constants.BufferOperation.discard_read_buffer)

    def __repr__(self):
        return "<VISAAdapter(resource='%s')>" % self.connection.resource_name
