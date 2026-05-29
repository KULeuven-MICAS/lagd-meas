# Copyright 2025 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

import logging
import struct
from types import TracebackType
from typing import List, Optional, Type

logger = logging.getLogger(__name__)

class WritePort:
	writePortCount = 0
	def __init__(self, devfile: str, width: int) -> None:

		if width%8 != 0:
			logger.error("width: %s is no multiple of 8 bits (1 byte)", width)
		else:
			self.devfile = devfile
			self.width = width
			self.portId = 0
			self.totalBytesForTransmission = 0
			self.totalBytesTransmitted = 0
			WritePort.writePortCount += 1
			self.port_open = False

	def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[TracebackType]) -> None:
		self.closePort()

	def openPort(self) -> bool:
		self.portId = open(self.devfile, 'wb',0)
		if self.portId == 0:
			logger.error("Could not open %s for write", self.devfile)
			return False
		else:
			self.port_open = True
			logger.info("Opened write port to %s", self.devfile)
			return True

	def closePort(self) -> None:
		self.portId.close()
		self.port_open = False
		logger.info("Closed write port to %s", self.devfile)

	def __sendData(self, data: bytes) -> bool:
		logger.debug("Sending %d bytes", len(data))
		self.portId.write(data)
		return True

	def sendString(self, data: bytes) -> bool:
		return self.__sendData(data)

	def sendByte(self, num: int) -> bool:
		data = struct.pack("B",num)
		return self.__sendData(data)

	def sendInt(self, num: int) -> bool:
		data = struct.pack("I",num)
		return self.__sendData(data)

	def sendIntArray(self, array: List[int]) -> bool:
		data = struct.pack("%si" % len(array),*array)
		return self.__sendData(data)

	def sendFloat(self, num: float) -> bool:
		data = struct.pack("f",num)
		return self.__sendData(data)

	def sendFloatArray(self, array: List[float]) -> bool:
		data = struct.pack("%sf" % len(array),*array)
		return self.__sendData(data)

	def sendDouble(self, num: float) -> bool:
		data = struct.pack("d",num)
		return self.__sendData(data)

	def sendDoubleArray(self, array: List[float]) -> bool:
		data = struct.pack("%sd" % len(array),*array)
		return self.__sendData(data)

	def sendHex(self, num: str) -> bool:
		data = struct.pack("I",int(num,0))
		return self.__sendData(data)

	def getBytesLost(self) -> int:
		return self.totalBytesForTransmission - self.totalBytesTransmitted
