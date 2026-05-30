# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

import os
import struct
import logging
import time
import numpy as np
from types import TracebackType
from typing import Optional, Tuple, Type, Union

logger = logging.getLogger(__name__)


class ReadPort:
	readPortCount = 0

	def __init__(self, devfile: str, width: int) -> None:
		if width%8 != 0:
			logger.error("width: %s is no multiple of 8 bits (1 byte)", width)
		else:
			self.devfile = devfile
			self.width = width
			self.nbBytes = width/8
			self.portId = 0
			self.port_open = False
			ReadPort.readPortCount += 1

	def __enter__(self) -> "ReadPort":
		self.openPort()
		return self

	def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[TracebackType]) -> None:
		self.closePort()

	def openPort(self) -> bool:
		try:
			self.portId = os.open(self.devfile, os.O_RDONLY | os.O_NONBLOCK)
		except OSError:
			logger.error("Could not open %s for read", self.devfile)
			return False
		self.port_open = True
		logger.info("Opened read port to %s", self.devfile)
		return True

	def closePort(self) -> None:
		os.close(self.portId)
		self.portId = 0
		self.port_open = False
		logger.info("Closed read port to %s", self.devfile)

	def readString(self, size: int) -> Union[bytes, str]:
		try:
			data = os.read(self.portId,size)
			return data
		except:
			return ""

	def readByte(self) -> Optional[int]:
		try:
			data = os.read(self.portId,1)
			return struct.unpack("B",data)[0]
		except:
			return None

	def readInt(self) -> Optional[int]:
		try:
			data = os.read(self.portId,4)
			return struct.unpack("I",data)[0]
		except:
			return None

	def readIntArray(self, length: int) -> np.ndarray:
		buffer = bytearray(length*4)
		offset = 0
		while offset<length*4:
			try:
				thesebytes = os.read(self.portId,4*length)
			except BlockingIOError:
				time.sleep(0.1)
				thesebytes = os.read(self.portId, 4 * length)
			buffer[offset:offset+len(thesebytes)] = thesebytes
			offset += len(thesebytes)
		return np.frombuffer(buffer, np.uint32)

	def readFloat(self) -> float:
		data = os.read(self.portId,4)
		return struct.unpack("f",data)[0]

	def readFloatArray(self, length: int) -> Tuple[float, ...]:
		data = os.read(self.portId,4*length)
		return struct.unpack("%sf" % length, data)

	def readDouble(self) -> float:
		data = os.read(self.portId,8)
		return struct.unpack("d",data)[0]

	def readDoubleArray(self, length: int) -> Tuple[float, ...]:
		data = os.read(self.portId,8*length)
		return struct.unpack("%sd" % length, data)

	def readHex(self) -> str:
		try:
			data = os.read(self.portId,4)
			return hex(struct.unpack("I",data)[0])
		except:
			return ""

	def flushBuffer(self, printData: bool = False) -> None:
		data = self.readInt()
		while data != None:
			if printData:
				print(hex(data))
			data = self.readInt()
