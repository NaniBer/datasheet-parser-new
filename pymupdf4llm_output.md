# ESP32-WROOM-32E ESP32-WROOM-32UE

## Datasheet Version 2.0

2.4 GHz Wi-Fi + Bluetooth [®] + Bluetooth LE module


Built around ESP32 series of SoCs, Xtensa [®] dual-core 32-bit LX6 microprocessor


4/8/16 MB flash available


26 GPIOs, rich set of peripherals


On-board PCB antenna or external antenna connector


ESP32-WROOM-32E ESP32-WROOM-32UE


www.espressif.com


1 Module Overview

#### 1 Module Overview


Note:


Check the link or the QR code to make sure that you use the latest version of this document:


[https://espressif.com/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf](https://espressif.com/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)

###### 1.1 Features



CPU and On-Chip Memory


_•_ ESP32-D0WD-V3 or ESP32-D0WDR2-V3


embedded, Xtensa dual-core 32-bit LX6


microprocessor, up to 240 MHz


_•_ 448 KB ROM


_•_ 520 KB SRAM


_•_ 16 KB SRAM in RTC


Wi-Fi


_•_ 802.11b/g/n


_•_ Bit rate: 802.11n up to 150 Mbps


_•_ A-MPDU and A-MSDU aggregation


_•_ 0.4 _µ_ s guard interval support


_•_ Center frequency range of operating channel:


2412 ~ 2484 MHz


Bluetooth [®]


_•_ Bluetooth V4.2 BR/EDR and Bluetooth LE


specification


_•_ Class-1, class-2 and class-3 transmitter


_•_ AFH


_•_ CVSD and SBC


Peripherals


_•_ Up to 26 GPIOs


–
5 strapping GPIOs


_•_ SD card, UART, SPI, SDIO, I2C, LED PWM, Motor


PWM, I2S, IR, pulse counter, GPIO, capacitive



touch sensor, ADC, DAC, TWAI [®] (compatible


with ISO 11898-1, i.e. CAN Specification 2.0)


Integrated Components on Module


_•_ 40 MHz crystal oscillator


_•_ 4/8/16 MB SPI flash


_•_ ESP32-D0WDR2-V3 also provides 2 MB PSRAM


Antenna Options


_•_ ESP32-WROOM-32E: On-board PCB antenna


_•_ ESP32-WROOM-32UE: external antenna via a


connector


Operating Conditions


_•_ Operating voltage/Power supply: 3.0 ~ 3.6 V


_•_ Operating ambient temperature:


– 85 °C version: –40 ~ 85 °C


– 105 °C version: –40 ~ 105 °C. Note that


only the modules embedded with a 4/8


MB flash support this version.


Certification


_•_ Bluetooth certification: BQB


_•_ RF certification: See certificates for


[ESP32-WROOM-32E](https://www.espressif.com/en/support/documents/certificates?keys=ESP32-WROOM-32E) [and ESP32-WROOM-32UE](https://www.espressif.com/en/support/documents/certificates?keys=ESP32-WROOM-32UE)


_•_ Green certification: REACH/RoHS


Test


_•_ HTOL/HTSL/uHAST/TCT/ESD



Espressif Systems 2 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


1 Module Overview

###### 1.2 Series Comparison


ESP32-WROOM-32E and ESP32-WROOM-32UE are two powerful, generic Wi-Fi MCU modules that have a rich


set of peripherals. They are an ideal choice for a wide variety of application scenarios related to Internet of


Things (IoT), such as embedded systems, smart home, wearable electronics, etc.


ESP32-WROOM-32E comes with a PCB antenna, and ESP32-WROOM-32UE with a connector for an external


antenna. The information in this datasheet is applicable to both modules.


The Series Comparison for the two modules is as follows:


Table 1: ESP32-WROOM-32E Series Comparison [1]



|Ordering Code|Flash2|PSRAM|Ambient Temp.3<br>(°C)|Size4<br>(mm)|
|---|---|---|---|---|
|ESP32-WROOM-32E-N4|4 MB (Quad SPI)|—|–40 ~ 85|18.0 × 25.5 × 3.1|
|ESP32-WROOM-32E-N8|8 MB (Quad SPI)|—|–40 ~ 85|–40 ~ 85|
|ESP32-WROOM-32E-N16|16 MB (Quad SPI)|—|–40 ~ 85|–40 ~ 85|
|ESP32-WROOM-32E-H4|4 MB (Quad SPI)|—|–40 ~ 105|–40 ~ 105|
|ESP32-WROOM-32E-H8|8 MB (Quad SPI)|—|–40 ~ 105|–40 ~ 105|
|ESP32-WROOM-32E-N4R2|4 MB (Quad SPI)|2 MB (Quad SPI)5|–40 ~ 85|–40 ~ 85|
|ESP32-WROOM-32E-N8R2|8 MB (Quad SPI)|2 MB (Quad SPI)5|–40 ~ 85|–40 ~ 85|
|ESP32-WROOM-32E-N16R2|16 MB (Quad SPI)|2 MB (Quad SPI)5|–40 ~ 85|–40 ~ 85|


1 This table shares the same notes presented in the table 2 below.


Table 2: ESP32-WROOM-32UE Series Comparison










|Ordering Code|Flash2|PSRAM|Ambient Temp.3<br>(°C)|Size4<br>(mm)|
|---|---|---|---|---|
|ESP32-WROOM-32UE-N4|4 MB (Quad SPI)|—|–40 ~ 85|18.0 × 19.2 × 3.2|
|ESP32-WROOM-32UE-N8|8 MB (Quad SPI)|—|–40 ~ 85|–40 ~ 85|
|ESP32-WROOM-32UE-N16|16 MB (Quad SPI)|—|–40 ~ 85|–40 ~ 85|
|ESP32-WROOM-32UE-H4|4 MB (Quad SPI)|—|–40 ~ 105|–40 ~ 105|
|ESP32-WROOM-32UE-H8|8 MB (Quad SPI)|—|–40 ~ 105|–40 ~ 105|
|ESP32-WROOM-32UE-N4R2|4 MB (Quad SPI)|2 MB (Quad SPI)5|–40 ~ 85|–40 ~ 85|
|ESP32-WROOM-32UE-N8R2|8 MB (Quad SPI)|2 MB (Quad SPI)5|–40 ~ 85|–40 ~ 85|
|ESP32-WROOM-32UE-N16R2|16 MB (Quad SPI)|2 MB (Quad SPI)5|–40 ~ 85|–40 ~ 85|



2
For specifications, refer to Section 6.5 _Memory Specifications_ .
3 Ambient temperature specifies the recommended temperature range of the environment immediately outside


the Espressif module.

4
For details, refer to Section 10.1 _Module Dimensions_ .
5 This module uses PSRAM integrated in the chip’s package.


At the core of the module is the ESP32-D0WD-V3 chip or ESP32-D0WDR2-V3 chip. The chip embedded is


designed to be scalable and adaptive. There are two CPU cores that can be individually controlled, and the


CPU clock frequency is adjustable from 80 MHz to 240 MHz. You can power off the CPU and make use of the


low-power coprocessor to constantly monitor the peripherals for changes or crossing of thresholds.


Espressif Systems 3 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


1 Module Overview


Note:


_•_ For more information on ESP32-D0WD-V3 and ESP32-D0WDR2-V3 chip, please refer to _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf)_ .


_•_ For chip revision identification, ESP-IDF release that supports a specific chip revision, and other information on


chip revisions, please refer to _[ESP32 Series SoC Errata](https://espressif.com/sites/default/files/documentation/esp32_errata_en.pdf#errata-chip-rev)_     - Section _Chip Revision_ .

###### 1.3 Applications




_•_ Smart Home


_•_ Industrial Automation


_•_ Health Care


_•_ Consumer Electronics


_•_ Smart Agriculture


_•_ POS Machines


_•_ Service Robot




_•_ Audio Devices


_•_ Generic Low-power IoT Sensor Hubs


_•_ Generic Low-power IoT Data Loggers


_•_ Cameras for Video Streaming


_•_ Speech Recognition


_•_ Image Recognition


_•_ SDIO Wi-Fi + Bluetooth Networking Card



Espressif Systems 4 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


Contents

#### Contents 1 Module Overview 2


1.1 Features 2


1.2 Series Comparison 3


1.3 Applications 4

#### 2 9 Block Diagram 3 Pin Definitions 10

3.1 Pin Layout 10


3.2 Pin Description 11

#### 4 13 Boot Configurations

4.1 Chip Boot Mode Control 14


4.2 Internal LDO (VDD_SDIO) Voltage Control 15


4.3 U0TXD Printing Control 16


4.4 Timing Control of SDIO Slave 16


4.5 JTAG Signal Source Control 16


4.6 Chip Power-up and Reset 16

#### 5 Peripherals 18

5.1 Peripheral Overview 18


5.2 Digital Peripherals 18


5.2.1 General Purpose Input / Output Interface (GPIO) 18


5.2.2 Serial Peripheral Interface (SPI) 18


5.2.3 Universal Asynchronous Receiver Transmitter (UART) 19


5.2.4 I2C Interface 19


5.2.5 I2S Interface 20


5.2.6 Remote Control Peripheral 20


5.2.7 Pulse Counter Controller (PCNT) 21


5.2.8 LED PWM Controller 21


5.2.9 Motor Control PWM 22


5.2.10 SD/SDIO/MMC Host Controller 23


5.2.11 SDIO/SPI Slave Controller 23


5.2.12 TWAI [®] Controller 24


5.2.13 Ethernet MAC Interface 24


5.3 Analog Peripherals 25


5.3.1 Analog-to-Digital Converter (ADC) 25


5.3.2 Digital-to-Analog Converter (DAC) 26


5.3.3 Touch Sensor 26

#### 6 Electrical Characteristics 28


6.1 Absolute Maximum Ratings 28


6.2 Recommended Operating Conditions 28


Espressif Systems 5 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


Contents


6.3 DC Characteristics (3.3 V, 25 °C) 28


6.4 Current Consumption Characteristics 29


6.5 Memory Specifications 30

#### 7 RF Characteristics 31


7.1 Wi-Fi Radio 31


7.1.1 Wi-Fi RF Transmitter (TX) Characteristics 31


7.1.2 Wi-Fi RF Receiver (RX) Characteristics 31


7.2 Bluetooth Radio 33


7.2.1 Receiver – Basic Data Rate 33


7.2.2 Transmitter – Basic Data Rate 33


7.2.3 Receiver – Enhanced Data Rate 34


7.2.4 Transmitter – Enhanced Data Rate 35


7.3 Bluetooth LE Radio 35


7.3.1 Receiver 35


7.3.2 Transmitter 36

#### 8 Module Schematics 37 9 Peripheral Schematics 39


40
#### 10 Physical Dimensions


10.1 Module Dimensions 40


10.2 Dimensions of External Antenna Connector 41

#### 11 43 PCB Layout Recommendations


11.1 PCB Land Pattern 43


11.2 Module Placement for PCB Design 45


46
#### 12 Product Handling

12.1 Storage Conditions 46


12.2 Electrostatic Discharge (ESD) 46


12.3 Reflow Profile 46


12.4 Ultrasonic Vibration 47


48
#### Datasheet Versioning Related Documentation and Resources 49


50
#### Revision History


Espressif Systems 6 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


List of Tables

#### List of Tables


1 ESP32-WROOM-32E Series Comparison [1] 3


2 ESP32-WROOM-32UE Series Comparison 3


3 Pin Definitions 11


4 Default Configuration of Strapping Pins 13


5 Description of Timing Parameters for the Strapping Pins 14


6 Chip Boot Mode Control 14


7 U0TXD Printing Control 16


8 Timing Control of SDIO Slave 16


9 Description of Timing Parameters for Power-up and Reset 17


10 ADC Characteristics 25


11 ADC Calibration Results 26


12 Capacitive-Sensing GPIOs Available on ESP32 26


13 Absolute Maximum Ratings 28


14 Recommended Operating Conditions 28


15 DC Characteristics (3.3 V, 25 °C) 28


16 Current Consumption Depending on RF Modes 29


17 Flash Specifications 30


18 PSRAM Specifications 30


19 Wi-Fi RF Characteristics 31


20 TX Power with Spectral Mask and EVM Meeting 802.11 Standards 31


21 RX Sensitivity 31


22 Maximum RX Level 32


23 RX Adjacent Channel Rejection 33


24 Bluetooth LE RF Characteristics 33


25 Receiver Characteristics – Basic Data Rate 33


26 Transmitter Characteristics – Basic Data Rate 34


27 Receiver Characteristics – Enhanced Data Rate 34


28 Transmitter Characteristics – Enhanced Data Rate 35


29 Receiver Characteristics – Bluetooth LE 35


30 Transmitter Characteristics – Bluetooth LE 36


Espressif Systems 7 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


List of Figures

#### List of Figures


1 ESP32-WROOM-32E Block Diagram 9


2 ESP32-WROOM-32UE Block Diagram 9


3 Pin Layout (Top View) 10


4 Visualization of Timing Parameters for the Strapping Pins 14


5 Chip Boot Flow 15


6 Visualization of Timing Parameters for Power-up and Reset 16


7 ESP32-WROOM-32E Schematics 37


8 ESP32-WROOM-32UE Schematics 38


9 Peripheral Schematics 39


10 ESP32-WROOM-32E Physical Dimensions 40


11 ESP32-WROOM-32UE Physical Dimensions 40


12 Dimensions of External Antenna Connector 41


13 ESP32-WROOM-32E Recommended PCB Land Pattern 43


14 ESP32-WROOM-32UE Recommended PCB Land Pattern 44


15 Reflow Profile 46


Espressif Systems 8 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


#### 2 Block Diagram























Figure 1: ESP32-WROOM-32E Block Diagram























Figure 2: ESP32-WROOM-32UE Block Diagram






3 Pin Definitions

#### 3 Pin Definitions

###### 3.1 Pin Layout


The pin diagram below shows the approximate location of pins on the module. For the actual diagram drawn to


scale, please refer to Figure 10.1 _Module Dimensions_ .


|Keepout Zone|Col2|Col3|Col4|
|---|---|---|---|
|Keepout Zone|Keepout Zone|Keepout Zone|Keepout Zone|
|Keepout Zone|Keepout Zone|||
|Keepout Zone||||





38


37


36


35


34


33


32


31


30


29


28


27


26


25



A





1


2


3


4


5


6


7


8


9


10


11


12


13


14













Figure 3: Pin Layout (Top View)


Note A:


_•_ The zone marked with dotted lines is the antenna keepout zone. The pin layout of ESP32-WROOM-32UE is the


same as that of ESP32-WROOM-32E, except that ESP32-WROOM-32UE has no keepout zone.


_•_ To learn more about the keepout zone for module’s antenna on the base board, please refer to


_[ESP32 Hardware Design Guidelines](https://espressif.com/documentation/esp32_hardware_design_guidelines_en.pdf)_     - Section _Positioning a Module on a Base Board_ .


Espressif Systems 10 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


3 Pin Definitions

###### 3.2 Pin Description


The module has 38 pins. See pin definitions in Table 3 _Pin Description_ .


For peripheral pin configurations, please refer to Section 5.2 _Digital Peripherals_ .


Table 3: Pin Definitions







|Name|No.|Type1|Function|
|---|---|---|---|
|GND|1|P|Ground|
|3V3|2|P|Power supply|
|EN|3|I|High: On; enables the chip<br>Low: Off; the chip shuts down<br>Note: Do not leave the pin foating.|
|SENSOR_VP|4|I|GPIO36, ADC1_CH0, RTC_GPIO0|
|SENSOR_VN|5|I|GPIO39, ADC1_CH3, RTC_GPIO3|
|IO34|6|I|GPIO34, ADC1_CH6, RTC_GPIO4|
|IO35|7|I|GPIO35, ADC1_CH7, RTC_GPIO5|
|IO32|8|I/O|GPIO32, XTAL_32K_P (32.768 kHz crystal oscillator input), ADC1_CH4,<br>TOUCH9, RTC_GPIO9|
|IO33|9|I/O|GPIO33, XTAL_32K_N (32.768 kHz crystal oscillator output),<br>ADC1_CH5, TOUCH8, RTC_GPIO8|
|IO25|10|I/O|GPIO25, DAC_1, ADC2_CH8, RTC_GPIO6, EMAC_RXD0|
|IO26|11|I/O|GPIO26, DAC_2, ADC2_CH9, RTC_GPIO7, EMAC_RXD1|
|IO27|12|I/O|GPIO27, ADC2_CH7, TOUCH7, RTC_GPIO17, EMAC_RX_DV|
|IO14|13|I/O|GPIO14, ADC2_CH6, TOUCH6, RTC_GPIO16, MTMS, HSPICLK,<br>HS2_CLK, SD_CLK, EMAC_TXD2|
|IO12|14|I/O|GPIO12, ADC2_CH5, TOUCH5, RTC_GPIO15, MTDI, HSPIQ, HS2_DATA2,<br>SD_DATA2, EMAC_TXD3|
|GND|15|P|Ground|
|IO13|16|I/O|GPIO13, ADC2_CH4, TOUCH4, RTC_GPIO14, MTCK, HSPID, HS2_DATA3,<br>SD_DATA3, EMAC_RX_ER|
|NC|17|-|See note 2|
|NC|18|-|See note 2|
|NC|19|-|See note 2|
|NC|20|-|See note 2|
|NC|21|-|See note 2|
|NC|22|-|See note 2|
|IO15|23|I/O|GPIO15, ADC2_CH3, TOUCH3, MTDO, HSPICS0, RTC_GPIO13,<br>HS2_CMD, SD_CMD, EMAC_RXD3|
|IO2|24|I/O|GPIO2, ADC2_CH2, TOUCH2, RTC_GPIO12, HSPIWP, HS2_DATA0,<br>SD_DATA0|
|IO0|25|I/O|GPIO0, ADC2_CH1, TOUCH1, RTC_GPIO11, CLK_OUT1, EMAC_TX_CLK|
|IO4|26|I/O|GPIO4, ADC2_CH0, TOUCH0, RTC_GPIO10, HSPIHD, HS2_DATA1,<br>SD_DATA1, EMAC_TX_ER|
|IO163|27|I/O|GPIO16, HS1_DATA4, U2RXD, EMAC_CLK_OUT|


Cont’d on next page


Espressif Systems 11 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


3 Pin Definitions


Table 3 – cont’d from previous page

|Name|No.|Type1|Function|
|---|---|---|---|
|IO17|28|I/O|GPIO17, HS1_DATA5, U2TXD, EMAC_CLK_OUT_180|
|IO5|29|I/O|GPIO5, VSPICS0, HS1_DATA6, EMAC_RX_CLK|
|IO18|30|I/O|GPIO18, VSPICLK, HS1_DATA7|
|IO19|31|I/O|GPIO19, VSPIQ, U0CTS, EMAC_TXD0|
|NC|32|-|-|
|IO21|33|I/O|GPIO21, VSPIHD, EMAC_TX_EN|
|RXD0|34|I/O|GPIO3, U0RXD, CLK_OUT2|
|TXD0|35|I/O|GPIO1, U0TXD, CLK_OUT3, EMAC_RXD2|
|IO22|36|I/O|GPIO22, VSPIWP, U0RTS, EMAC_TXD1|
|IO23|37|I/O|GPIO23, VSPID, HS1_STROBE|
|GND|38|P|Ground|



1 P: power supply; I: input; O: output.
2 Pins GPIO6 to GPIO11 on the ESP32-D0WD-V3/ESP32-D0WDR2-V3 chip are connected to the SPI flash


integrated on the module and are not led out.
3 In module variants that have embedded QSPI PSRAM, i.e., that embed ESP32-D0WDR2-V3, IO16 is


connected to the embedded PSRAM and can not be used for other functions.


Espressif Systems 12 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


4 Boot Configurations

#### 4 Boot Configurations


Note:


The content below is excerpted from _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-pins-strap)_  - Section _Boot Configurations_ . For the strapping pin


mapping between the chip and modules, please refer to Chapter 8 _Module Schematics_ .


The chip allows for configuring the following boot parameters through strapping pins and eFuse bits at


power-up or a hardware reset, without microcontroller interaction.


_•_ Chip boot mode


–
Strapping pin: GPIO0 and GPIO2


_•_ Internal LDO (VDD_SDIO) Voltage


–
Strapping pin: MTDI


–
eFuse bit: EFUSE_SDIO_FORCE and EFUSE_SDIO_TIEH


_•_ U0TXD printing


–
Strapping pin: MTDO


_•_ Timing of SDIO Slave


–
Strapping pin: MTDO and GPIO5


_•_ JTAG signal source


–
eFuse bit: EFUSE_DISABLE_JTAG


The default values of all the above eFuse bits are 0, which means that they are not burnt. Given that eFuse is


one-time programmable, once an eFuse bit is programmed to 1, it can never be reverted to 0. For how to


program eFuse bits, please refer to _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#efuse)_ - Chapter _eFuse Controller_ .


The default values of the strapping pins, namely the logic levels, are determined by pins’ internal weak


pull-up/pull-down resistors at reset if the pins are not connected to any circuit, or connected to an external


high-impedance circuit.


Table 4: Default Configuration of Strapping Pins

|Strapping Pin|Default Configuration|Bit Value|
|---|---|---|
|GPIO0|Pull-up|1|
|GPIO2|Pull-down|0|
|MTDI|Pull-down|0|
|MTDO|Pull-up|1|
|GPIO5|Pull-up|1|



To change the bit values, the strapping pins should be connected to external pull-down/pull-up resistances. If


the ESP32 is used as a device by a host MCU, the strapping pin voltage levels can also be controlled by the


host MCU.


All strapping pins have latches. At system reset, the latches sample the bit values of their respective strapping


pins and store them until the chip is powered down or shut down. The states of latches cannot be changed in


Espressif Systems 13 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


4 Boot Configurations


any other way. It makes the strapping pin values available during the entire chip operation, and the pins are


freed up to be used as regular IO pins after reset.


The timing of signals connected to the strapping pins should adhere to the _setup time_ and _hold time_


specifications in Table 5 and Figure 4.


Table 5: Description of Timing Parameters for the Strapping Pins





|Parameter|Description|Min (ms)|
|---|---|---|
|t_SU_|_Setup time_ is the time reserved for the power rails to stabilize be-<br>fore the CHIP_PU pin is pulled high to activate the chip.|0|
|t_H_|_Hold time_ is the time reserved for the chip to read the strapping<br>pin values after CHIP_PU is already high and before these pins<br>start operating as regular IO pins.|1|


CHIP_PU


Strapping pin

|Col1|tSU|tH|Col4|
|---|---|---|---|
|V_IH_nRST_||||
|V_IH_nRST_||||
|V_IH_nRST_||||



Figure 4: Visualization of Timing Parameters for the Strapping Pins






###### 4.1 Chip Boot Mode Control

GPIO0 and GPIO2 control the boot mode after the reset is released. See Table 6 _Chip Boot Mode_


_Control_ .


Table 6: Chip Boot Mode Control

|Boot Mode|GPIO0|GPIO2|
|---|---|---|
|SPI Boot Mode|1|Any value|
|Joint Download Boot Mode 2|0|0|



1 Bold marks the default value and configuration.
2 Joint Download Boot mode supports the following


download methods:


_•_ SDIO Download Boot


_•_ UART Download Boot


In Joint Download Boot mode, the detailed boot flow of the chip is put below 5.


Espressif Systems 14 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


4 Boot Configurations


Figure 5: Chip Boot Flow


uart_download_dis controls boot mode behaviors:


It permanently disables Download Boot mode when uart_download_dis is set to 1 (valid only for ESP32 chip


revisions v3.0 and higher).

###### 4.2 Internal LDO (VDD_SDIO) Voltage Control


MTDI is used to select the VDD_SDIO power supply voltage at reset:


_•_ MTDI = 0 (by default), VDD_SDIO pin is powered directly from VDD3P3_RTC. Typically this voltage is 3.3


V. For more information, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-pwr-scheme)_    - Section _Power Scheme_ .


_•_ MTDI = 1, VDD_SDIO pin is powered from internal 1.8 V LDO.


This functionality can be overridden by setting EFUSE_SDIO_FORCE to 1, in which case the EFUSE_SDIO_TIEH


determines the VDD_SDIO voltage:


_•_ EFUSE_SDIO_TIEH = 0, VDD_SDIO connects to 1.8 V LDO.


_•_ EFUSE_SPI_TIEH = 1, VDD_SDIO connects to VDD3P3_RTC.


Espressif Systems 15 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


4 Boot Configurations

###### 4.3 U0TXD Printing Control


During booting, the strapping pin MTDO can be used to control the U0TXD Printing, as Table 7 shows.


Table 7: U0TXD Printing Control

|U0TXD Printing Control|MTDO|
|---|---|
|Enabled 1|1|
|Disabled|0|



1 Bold marks the default value and


configuration.

###### 4.4 Timing Control of SDIO Slave


The strapping pin MTDO and GPIO5 can be used to control the timing of SDIO slave, see Table 8 _Timing_


_Control of SDIO Slave_ .


Table 8: Timing Control of SDIO Slave

|Edge behavior|MTDO|GPIO5|
|---|---|---|
|Falling edge sampling, falling edge output|0|0|
|Falling edge sampling, rising edge output|0|1|
|Rising edge sampling, falling edge output|1|0|
|Rising edge sampling, rising edge output|1|1|



1 Bold marks the default value and configuration.

###### 4.5 JTAG Signal Source Control


If EFUSE_DISABLE_JTAG is set to 1, the source of JTAG signals can be disabled.

###### 4.6 Chip Power-up and Reset


Once the power is supplied to the chip, its power rails need a short time to stabilize. After that, CHIP_PU – the


pin used for power-up and reset – is pulled high to activate the chip. For information on CHIP_PU as well as


power-up and reset timing, see Figure 6 and Table 9.


VDD


CHIP_PU

|Col1|tST BL|Col3|tRST|Col5|
|---|---|---|---|---|
|V_IL_nRST_<br>DD3P3_RTC Min|||||
|V_IL_nRST_<br>DD3P3_RTC Min|||||
|V_IL_nRST_<br>DD3P3_RTC Min|||||



Figure 6: Visualization of Timing Parameters for Power-up and Reset


Espressif Systems 16 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


4 Boot Configurations


Table 9: Description of Timing Parameters for Power-up and Reset






|Parameter|Description|Min (µs)|
|---|---|---|
|t_ST BL_|Time reserved for the 3.3 V rails to stabilize before the CHIP_PU<br>pin is pulled high to activate the chip|50|
|t_RST_|Time reserved for CHIP_PU to stay below V_IL_nRST_ to reset the<br>chip (see Table 15)|50|



For details, please refer to _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-pwr-up-reset)_ - Section _Chip Power-up and Reset_ .


Espressif Systems 17 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals

#### 5 Peripherals

###### 5.1 Peripheral Overview


ESP32-D0WD-V3 chip and ESP32-D0WDR2-V3 chip integrate a rich set of peripherals including SPI, I2S,


UART, I2C, pulse count controller, TWAI [®], ADC, DAC, touch sensor, etc.


To learn more about on-chip components, please refer to _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-func-descr)_ - Section _Functional_


_Description_ .


Note:


_•_ The content below is sourced from _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-func-descr)_    - Section _Functional Description_ . Some information


may not be applicable to ESP32-WROOM-32E and ESP32-WROOM-32UE as not all the IO signals are exposed


on the module.


_•_ To learn more about peripheral signals, please refer to _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_    - Section _Peripheral_


_Signal List_ .

###### 5.2 Digital Peripherals


5.2.1 General Purpose Input / Output Interface (GPIO)


ESP32 has 34 GPIO pins which can be assigned various functions by programming the appropriate registers.


There are several kinds of GPIOs: digital-only, analog-enabled, capacitive-touch-enabled, etc. Analog-enabled


GPIOs and Capacitive-touch-enabled GPIOs can be configured as digital GPIOs.


Most of the digital GPIOs can be configured as internal pull-up or pull-down, or set to high impedance. When


configured as an input, the input value can be read through the register. The input can also be set to


edge-trigger or level-trigger to generate CPU interrupts. Most of the digital IO pins are bi-directional,


non-inverting and tristate, including input and output buffers with tristate control. These pins can be


multiplexed with other functions, such as the SDIO, UART, SPI, etc. (More details can be found in


_[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-io-mux)_ - Appendix, Table _IO_MUX_ . ) For low-power operations, the GPIOs can be set to hold


their states.


5.2.2 Serial Peripheral Interface (SPI)


ESP32 integrates four SPI controllers which can be used to communicate with external devices that use the


SPI protocol. Controller SPI0 is used as a buffer for accessing external memory. Controller SPI1 can be used


as a master. Controllers SPI2 and SPI3 can be configured as either a master or a slave.


SPI1, SPI2, and SPI3 use signal buses prefixed with SPI, HSPI, and VSPI, respectively.


Features of General Purpose SPI (GP-SPI)


_•_ Programmable data transfer length, in multiples of 1 byte


_•_ Four-line full-duplex/half-duplex communication and three-line half-duplex communication support


_•_ Master mode and slave mode


Espressif Systems 18 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


_•_ Programmable CPOL and CPHA


_•_ Programmable clock


Pin Assignment


For SPI, the pins are multiplexed with GPIO6 ~ GPIO11 via the IO MUX. For HSPI, the pins are multiplexed with


GPIO2, GPIO4, GPIO12 ~ GPIO15 via the IO MUX. For VSPI, the pins are multiplexed with GPIO5, GPIO18 ~


GPIO19, GPIO21 ~ GPIO23 via the IO MUX.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.3 Universal Asynchronous Receiver Transmitter (UART)


The UART in the ESP32 chip facilitates the transmission and reception of asynchronous serial data between


the chip and external UART devices. It consists of two UARTs in the main system, and one low-power LP


UART.


Feature List


_•_ Programmable baud rates up to 5 MBaud


_•_ RAM shared by TX FIFOs and RX FIFOs


_•_ Supports input baud rate self-check


_•_ Support for various lengths of data bits and stop bits


_•_ Parity bit support


_•_ Asynchronous communication (RS232 and RS485) and IrDA support


_•_ Supports DMA to communicate data in high speed


_•_ Supports UART wake-up


_•_ Supports both software and hardware flow control


Pin Assignment


The pins for UART can be chosen from any GPIOs via the GPIO Matrix.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.4 I2C Interface


ESP32 has two I2C bus interfaces which can serve as I2C master or slave, depending on the user’s


configuration.


Feature List


_•_ Two I2C controllers: one in the main system and one in the low-power system


_•_ Standard mode (100 Kbit/s)


Espressif Systems 19 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


_•_ Fast mode (400 Kbit/s)


_•_ Up to 5 MHz, yet constrained by SDA pull-up strength


_•_ Support for 7-bit and 10-bit addressing, as well as dual address mode


_•_ Supports continuous data transmission with disabled Serial Clock Line (SCL)


_•_ Supports programmable digital noise filter


Users can program command registers to control I2C interfaces, so that they have more flexibility.


Pin Assignment


For regular I2C, the pins used can be chosen from any GPIOs via the GPIO Matrix.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.5 I2S Interface


The I2S Controller in the ESP32 chip provides a flexible communication interface for streaming digital data in


multimedia applications, particularly digital audio applications.


Feature List


_•_ Master mode and slave mode


_•_ Full-duplex and half-duplex communications


_•_ A variety of audio standards supported


_•_ Configurable high-precision output clock


_•_ Supports PDM signal input and output


_•_ Configurable data transmit and receive modes


Pin Assignment


The pins for the I2S Controller can be chosen from any GPIOs via the GPIO Matrix.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.6 Remote Control Peripheral


The Remote Control Peripheral (RMT) controls the transmission and reception of infrared remote control


signals.


Feature List


_•_ Eight channels for sending and receiving infrared remote control signals


_•_ Independent transmission and reception capabilities for each channel


_•_ Clock divider counter, state machine, and receiver for each RX channel


Espressif Systems 20 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


_•_ Supports various infrared protocols


Pin Assignment


The pins for the Remote Control Peripheral can be chosen from any GPIOs via the GPIO Matrix.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.7 Pulse Counter Controller (PCNT)


The pulse counter controller (PCNT) is designed to count input pulses by tracking rising and falling edges of


the input pulse signal.


Feature List


_•_ Eight independent pulse counter units


_•_ Each pulse counter unit has a 16-bit signed counter register and two channels


_•_ Counter modes: increment, decrement, or disable


_•_ Glitch filtering for input pulse signals and control signals


_•_ Selection between counting on rising or falling edges of the input pulse signal


Pin Assignment


The pins for the Pulse Count Controller can be chosen from any GPIOs via the GPIO Matrix.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.8 LED PWM Controller


The LED PWM Controller (LEDC) is designed to generate PWM signals for LED control.


Feature List


_•_ Sixteen independent PWM generators


_•_ Maximum PWM duty cycle resolution of 20 bits


_•_ Eight independent timers with 20-bit counters, configurable fractional clock dividers and counter


overflow values


_•_ Adjustable phase of PWM signal output


_•_ PWM duty cycle dithering


_•_ Automatic duty cycle fading


Pin Assignment


The pins for the LED PWM Controller can be chosen from any GPIOs via the GPIO Matrix.


Espressif Systems 21 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.9 Motor Control PWM


The Pulse Width Modulation (PWM) controller can be used for driving digital motors and smart lights. The


controller consists of PWM timers, the PWM operator and a dedicated capture sub-module. Each timer


provides timing in synchronous or independent form, and each PWM operator generates a waveform for one


PWM channel. The dedicated capture sub-module can accurately capture events with external timing.


Feature List


_•_ Three PWM timers for precise timing and frequency control


–
Every PWM timer has a dedicated 8-bit clock prescaler


–
The 16-bit counter in the PWM timer can work in count-up mode, count-down mode, or


count-up-down mode


–
A hardware sync can trigger a reload on the PWM timer with a phase register. It will also trigger the


prescaler’ restart, so that the timer’s clock can also be synced, with selectable hardware


synchronization source


_•_ Three PWM operators for generating waveform pairs


–
Six PWM outputs to operate in several topologies


–
Configurable dead time on rising and falling edges; each set up independently


–
Modulating of PWM output by high-frequency carrier signals, useful when gate drivers are insulated


with a transformer


_•_ Fault Detection module


–
Programmable fault handling in both cycle-by-cycle mode and one-shot mode


–
A fault condition can force the PWM output to either high or low logic levels


_•_ Capture module for hardware-based signal processing


–
Speed measurement of rotating machinery


–
Measurement of elapsed time between position sensor pulses


–
Period and duty cycle measurement of pulse train signals


–
Decoding current or voltage amplitude derived from duty-cycle-encoded signals of current/voltage


sensors


–
Three individual capture channels, each of which with a 32-bit time-stamp register


–
Selection of edge polarity and prescaling of input capture signals


–
The capture timer can sync with a PWM timer or external signals


Pin Assignment


The pins for the Motor Control PWM can be chosen from any GPIOs via the GPIO Matrix.


Espressif Systems 22 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.10 SD/SDIO/MMC Host Controller


An SD/SDIO/MMC host controller is available on ESP32.


Feature List


_•_ Supports two external cards


_•_ Supports SD Memory Card standard: version 3.0 and version 3.01)


_•_ Supports SDIO Version 3.0


_•_ Supports Consumer Electronics Advanced Transport Architecture (CE-ATA Version 1.1)


_•_ Supports Multimedia Cards (MMC version 4.41, eMMC version 4.5 and version 4.51)


The controller allows up to 80 MHz clock output in three different data-bus modes: 1-bit, 4-bit, and 8-bit


modes. It supports two SD/SDIO/MMC4.41 cards in a 4-bit data-bus mode. It also supports one SD card


operating at 1.8 V.


Pin Assignment


The pins for SD/SDIO/MMC Host Controller are multiplexed with GPIO2, GPIO4, GPIO6 ~ GPIO15 via IO


MUX.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.11 SDIO/SPI Slave Controller


ESP32 integrates an SD device interface that conforms to the industry-standard SDIO Card Specification


Version 2.0, and allows a host controller to access the SoC, using the SDIO bus interface and protocol. ESP32


acts as the slave on the SDIO bus. The host can access the SDIO-interface registers directly and can access


shared memory via a DMA engine, thus maximizing performance without engaging the processor cores.


Feature List


The SDIO/SPI slave controller supports the following features:


_•_ SPI, 1-bit SDIO, and 4-bit SDIO transfer modes over the full clock range from 0 to 50 MHz


_•_ Configurable sampling and driving clock edge


_•_ Special registers for direct access by host


_•_ Interrupts to host for initiating data transfer


_•_ Automatic loading of SDIO bus data and automatic discarding of padding data


_•_ Block size of up to 512 bytes


_•_ Interrupt vectors between the host and the slave, allowing both to interrupt each other


_•_ Supports DMA for data transfer


Espressif Systems 23 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


Pin Assignment


The pins for SDIO/SPI Slave Controller are multiplexed with GPIO2, GPIO4, GPIO6 ~ GPIO15 via IO MUX.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.12 TWAI [®] Controller


The Two-wire Automotive Interface (TWAI [®] ) is a multi-master, multi-cast communication protocol designed for


automotive applications. The TWAI controller facilitates the communication based on this protocol.


Feature List


_•_ Compatible with ISO 11898-1 protocol (CAN Specification 2.0)


_•_ Standard frame format (11-bit ID) and extended frame format (29-bit ID)


_•_ Bit rates:


–
From 25 Kbit/s to 1 Mbit/s in chip revision v0.0/v1.0/v1.1


–
From 12.5 Kbit/s to 1 Mbit/s in chip revision v3.0/v3.1


_•_ Multiple modes of operation: Normal, Listen Only, and Self-Test


_•_ 64-byte receive FIFO


_•_ Special transmissions: single-shot transmissions and self reception


_•_ Acceptance filter (single and dual filter modes)


_•_ Error detection and handling: error counters, configurable error interrupt threshold, error code capture,


arbitration lost capture


Pin Assignment


The pins for the Two-wire Automotive Interface can be chosen from any GPIOs via the GPIO Matrix.


For more information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin_


_Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.2.13 Ethernet MAC Interface


An IEEE-802.3-2008-compliant Media Access Controller (MAC) is provided for Ethernet LAN communications.


ESP32 requires an external physical interface device (PHY) to connect to the physical LAN bus (twisted-pair,


fiber, etc.). The PHY is connected to ESP32 through 17 signals of MII or nine signals of RMII.


Feature List


_•_ 10 Mbps and 100 Mbps rates


_•_ Dedicated DMA controller allowing high-speed transfer between the dedicated SRAM and Ethernet MAC


_•_ Tagged MAC frame (VLAN support)


_•_ Half-duplex (CSMA/CD) and full-duplex operation


Espressif Systems 24 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


_•_ MAC control sublayer (control frames)


_•_ 32-bit CRC generation and removal


_•_ Several address-filtering modes for physical and multicast address (multicast and group addresses)


_•_ 32-bit status code for each transmitted or received frame


_•_ Internal FIFOs to buffer transmit and receive frames. The transmit FIFO and the receive FIFO are both 512


words (32-bit)


_•_ Hardware PTP (Precision Time Protocol) in accordance with IEEE 1588 2008 (PTP V2)


_•_ 25 MHz/50 MHz clock output


Pin Assignment


For information about the pin assignment of Ethernet MAC Interface, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section


_Peripheral Pin Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO_


_Matrix_ .

###### 5.3 Analog Peripherals


5.3.1 Analog-to-Digital Converter (ADC)


ESP32 integrates two 12-bit SAR ADCs and supports measurements on 18 channels (analog-enabled pins).


The ULP coprocessor in ESP32 is also designed to measure voltage, while operating in the sleep mode, which


enables low-power consumption. The CPU can be woken up by a threshold setting and/or via other


triggers.


Table 10 describes the ADC characteristics.


Table 10: ADC Characteristics

|Parameter|Description|Min|Max|Unit|
|---|---|---|---|---|
|DNL (Differential nonlinearity)|RTC controller; ADC connected to an<br>external 100 nF capacitor; DC signal input;<br>ambient temperature at 25 °C;<br>Wi-Fi&Bluetooth off|–7|7|LSB|
|INL (Integral nonlinearity)|INL (Integral nonlinearity)|–12|12|LSB|
|Sampling rate|RTC controller<br>DIG controller|—|200|ksps|
|Sampling rate|RTC controller<br>DIG controller|—|2|Msps|



Notes:


_•_ When atten = 3 and the measurement result is above 3000 (voltage at approx. 2450 mV), the ADC


accuracy will be worse than described in the table above.


_•_ To get better DNL results, users can take multiple sampling tests with a filter, or calculate the average


value.


_•_ The input voltage range of GPIO pins within VDD3P3_RTC domain should strictly follow the DC


characteristics provided in Table 15. Otherwise, measurement errors may be introduced, and chip


performance may be affected.


Espressif Systems 25 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


By default, there are ±6% differences in measured results between chips. ESP-IDF provides couple of


[calibration methods](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/adc_calibration.html) for ADC1. Results after calibration using eFuse Vref value are shown in Table 11. For higher


accuracy, users may apply other calibration methods provided in ESP-IDF, or implement their own.


Table 11: ADC Calibration Results



|Parameter|Description|Min|Max|Unit|
|---|---|---|---|---|
|Total error|Atten = 0, effective measurement range of 100_ ∼_950 mV|–23|23|mV|
|Total error|Atten = 1, effective measurement range of 100_ ∼_1250 mV|–30|30|mV|
|Total error|Atten = 2, effective measurement range of 150_ ∼_1750 mV|–40|40|mV|
|Total error|Atten = 3, effective measurement range of 150_ ∼_2450 mV|–60|60|mV|


Pin Assignment





With appropriate settings, the ADCs can be configured to measure voltage on 18 pins maximum. For detailed


information about the pin assignment, see _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin Configurations_


and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ - Chapter _IO_MUX and GPIO Matrix_ .


5.3.2 Digital-to-Analog Converter (DAC)


Two 8-bit DAC channels can be used to convert two digital signals into two analog voltage signal outputs. The


design structure is composed of integrated resistor strings and a buffer. This dual DAC supports power supply


as input voltage reference. The two DAC channels can also support independent conversions.


Pin Assignment


The DAC can be configured by GPIO 25 and GPIO 26. For detailed information about the pin assignment, see


_[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf#cd-peri-pin-config)_ - Section _Peripheral Pin Configurations_ and _[ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf#iomuxgpio)_ 

Chapter _IO_MUX and GPIO Matrix_ .


5.3.3 Touch Sensor


ESP32 has 10 capacitive-sensing GPIOs, which detect variations induced by touching or approaching the


GPIOs with a finger or other objects. The low-noise nature of the design and the high sensitivity of the circuit


allow relatively small pads to be used. Arrays of pads can also be used, so that a larger area or more points


can be detected.


Pin Assignment


The 10 capacitive-sensing GPIOs are listed in Table 12.


Table 12: Capacitive-Sensing GPIOs Available on ESP32

|Capacitive-Sensing Signal Name|Pin Name|
|---|---|
|T0|GPIO4|
|T1|GPIO0|
|T2|GPIO2|
|T3|MTDO|
|T4|MTCK|



Espressif Systems 26 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


5 Peripherals


Note:




|Capacitive-Sensing Signal Name|Pin Name|
|---|---|
|T5|MTDI|
|T6|MTMS|
|T7|GPIO27|
|T8|32K_XN|
|T9|32K_XP|



ESP32 Touch Sensor has not passed the Conducted Susceptibility (CS) test for now, and thus has limited application


scenarios.


Espressif Systems 27 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


6 Electrical Characteristics

#### 6 Electrical Characteristics

###### 6.1 Absolute Maximum Ratings


Stresses above those listed in _Absolute Maximum Ratings_ may cause permanent damage to the device.


These are stress ratings only and functional operation of the device at these or any other conditions beyond


those indicated under _Recommended Operating Conditions_ is not implied. Exposure to


absolute-maximum-rated conditions for extended periods may affect device reliability.


Table 13: Absolute Maximum Ratings

|Symbol|Parameter|Min|Max|Unit|
|---|---|---|---|---|
|VDD33|Power supply voltage|–0.3|3.6|V|
|T_ST ORE_|Storage temperature|–40|105|°C|



                       - Please see Appendix IO MUX of


_[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf)_ for IO’s power domain.

###### 6.2 Recommended Operating Conditions


Table 14: Recommended Operating Conditions

|Symbol|Parameter|Col3|Min|Typ|Max|Unit|
|---|---|---|---|---|---|---|
|VDD33|Power supply voltage|Power supply voltage|3.0|3.3|3.6|V|
|I_V DD_|Current delivered by external power supply|Current delivered by external power supply|0.5|—|—|A|
|T|Operating ambient temperature|85 °C version|–40|—|85|°C|
|T|Operating ambient temperature|105 °C version|105 °C version|105 °C version|105|105|


###### 6.3 DC Characteristics (3.3 V, 25 °C)


Table 15: DC Characteristics (3.3 V, 25 °C)

|Symbol|Parameter|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
|C_IN_|Pin capacitance|—|2|—<br>|pF|
|V_IH_|High-level input voltage|0.75 × VDD1|—|VDD1 + 0.3|V|
|V_IL_|Low-level input voltage|–0.3|—|0.25 × VDD1|V|
|I_IH_|High-level input current|—|—|50|nA|
|I_IL_|Low-level input current|—|—|50|nA|
|V_OH_|High-level output voltage|0.8 × VDD1|—|—|V|
|V_OL_|Low-level output voltage|—|—|0.1 × VDD1|V|



Cont’d on next page


Espressif Systems 28 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


6 Electrical Characteristics


Table 15 – cont’d from previous page
























|Symbol|Parameter|Col3|Min|Typ|Max|Unit|
|---|---|---|---|---|---|---|
|I_OH_|High-level source current<br>(VDD1 = 3.3 V,<br>V_OH_ >= 2.64 V,<br>output drive strength set<br>to the maximum)|VDD3P3_CPU<br>power<br>domain<br>1, 2|—|40|—|mA|
|I_OH_|High-level source current<br>(VDD1 = 3.3 V,<br>V_OH_ >= 2.64 V,<br>output drive strength set<br>to the maximum)|VDD3P3_RTC<br>power<br>domain<br>1, 2|—|40|—|mA|
|I_OH_|High-level source current<br>(VDD1 = 3.3 V,<br>V_OH_ >= 2.64 V,<br>output drive strength set<br>to the maximum)|VDD_SDIO power<br>domain 1, 3|—|20|—|mA|
|I_OL_|Low-level sink current<br>(VDD1 = 3.3 V, V_OL_ = 0.495 V,<br>output drive strength set to the maximum)|Low-level sink current<br>(VDD1 = 3.3 V, V_OL_ = 0.495 V,<br>output drive strength set to the maximum)|—|28|—|mA|
|R_P U_|Resistance of internal pull-up resistor|Resistance of internal pull-up resistor|—|45|—|kΩ|
|R_P D_|Resistance of internal pull-down resistor|Resistance of internal pull-down resistor|—|45|—|kΩ|
|V_IH_nRST_|Chip reset release voltage (CHIP_PU voltage<br>is within the specifed range)|Chip reset release voltage (CHIP_PU voltage<br>is within the specifed range)|0.75 × VDD 1|—|VDD 1 + 0.3|V|
|V_IL_nRST_|Low-level input voltage of CHIP_PU<br>to shut down the chip|Low-level input voltage of CHIP_PU<br>to shut down the chip|—|—|0.6|V|



1 Please see Appendix IO MUX of _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf)_ for IO’s power domain. VDD is the I/O voltage


for a particular power domain of pins.
2 For VDD3P3_CPU and VDD3P3_RTC power domain, per-pin current sourced in the same domain is


gradually reduced from around 40 mA to around 29 mA, V _OH_ >=2.64 V, as the number of current-source


pins increases.
3 Pins occupied by flash and/or PSRAM in the VDD_SDIO power domain were excluded from the test.

###### 6.4 Current Consumption Characteristics


Owing to the use of advanced power-management technologies, the module can switch between different


power modes. For details on different power modes, please refer to Section _RTC and Low-Power_


_Management_


in _[ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf)_ .


The current consumption measurements are taken with a 3.3 V supply at 25 °C ambient temperature.


TX current consumption is rated at a 100% duty cycle.


RX current consumption is rated when the peripherals are disabled and the CPU idle.


Table 16: Current Consumption Depending on RF Modes









|Work mode|Description|Col3|Average (mA)|Peak (mA)|
|---|---|---|---|---|
|Active (RF working)|TX|802.11b, 20 MHz, 1 Mbps, @19.5 dBm|239|379|
|Active (RF working)|TX|802.11g, 20 MHz, 54 Mbps, @15 dBm|190|276|
|Active (RF working)|TX|802.11n, 20 MHz, MCS7, @13 dBm|183|258|
|Active (RF working)|TX|802.11n, 40 MHz, MCS7, @13 dBm|165|211|
|Active (RF working)|RX|802.11b/g/n, 20 MHz|112|112|
|Active (RF working)|RX|802.11n, 40 MHz|118|118|


Espressif Systems 29 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


6 Electrical Characteristics

###### 6.5 Memory Specifications


The data below is sourced from the memory vendor datasheet. These values are guaranteed through design


and/or characterization but are not fully tested in production. Devices are shipped with the memory


erased.


Table 17: Flash Specifications





|Parameter|Description|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
|VCC|Power supply voltage (1.8 V)|1.65|1.80|2.00|V|
|VCC|Power supply voltage (3.3 V)|2.7|3.3|3.6|V|
|F_C_|Maximum clock frequency|80|—|—|MHz|
|—|Program/erase cycles|100,000|—|—|cycles|
|T_RET_|Data retention time|20|—|—|years|
|T_P P_|Page program time|—|0.8|5|ms|
|T_SE_|Sector erase time (4 KB)|—|70|500|ms|
|T_BE_1|Block erase time (32 KB)|—|0.2|2|s|
|T_BE_2|Block erase time (64 KB)|—|0.3|3|s|
|T_CE_|Chip erase time (16 Mb)|—|7|20|s|
|T_CE_|Chip erase time (32 Mb)|—|20|60|s|
|T_CE_|Chip erase time (64 Mb)|—|25|100|s|
|T_CE_|Chip erase time (128 Mb)|—|60|200|s|
|T_CE_|Chip erase time (256 Mb)|—|70|300|s|


Table 18: PSRAM Specifications



|Parameter|Description|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
|VCC|Power supply voltage (1.8 V)|1.62|1.80|1.98|V|
|VCC|Power supply voltage (3.3 V)|2.7|3.3|3.6|V|
|F_C_|Maximum clock frequency|80|—|—|MHz|


Espressif Systems 30 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


7 RF Characteristics

#### 7 RF Characteristics


This section contains tables with RF characteristics of the Espressif product.


The RF data is measured at the antenna port, where RF cable is connected, including the front-end loss. The


external antennas used for the tests on the modules with external antenna connectors have an impedance of


50 Ω.Devices should operate in the center frequency range allocated by regional regulatory authorities. The


[target center frequency range and the target transmit power are configurable by software. See ESP RF Test](https://www.espressif.com/en/support/download/other-tools?keys=RF+Test+Tool)


[Tool and Test Guide](https://www.espressif.com/en/support/download/other-tools?keys=RF+Test+Tool) for instructions.


Unless otherwise stated, the RF tests are conducted with a 3.3 V (±5%) supply at 25 ºC ambient temperature.

###### 7.1 Wi-Fi Radio


Table 19: Wi-Fi RF Characteristics

|Name|Description|
|---|---|
|Center frequency range of operating channel|2412 ~ 2484 MHz|
|Wi-Fi wireless standard|IEEE 802.11b/g/n|



7.1.1 Wi-Fi RF Transmitter (TX) Characteristics


Table 20: TX Power with Spectral Mask and EVM Meeting 802.11 Standards

|Rate|Min<br>(dBm)|Typ<br>(dBm)|Max<br>(dBm)|
|---|---|---|---|
|802.11b, 1 Mbps|—|19.5|—|
|802.11b, 11 Mbps|—|19.5|—|
|802.11g, 6 Mbps|—|18.0|—|
|802.11g, 54 Mbps|—|14.0|—|
|802.11n, HT20, MCS0|—|18.0|—|
|802.11n, HT20, MCS7|—|13.0|—|
|802.11n, HT40, MCS0|—|18.0|—|
|802.11n, HT40, MCS7|—|13.0|—|



7.1.2 Wi-Fi RF Receiver (RX) Characteristics


For RX tests, the PER (packet error rate) limit is 8% for 802.11b, and 10% for 802.11g/n.


Table 21: RX Sensitivity

|Rate|Min<br>(dBm)|Typ<br>(dBm)|Max<br>(dBm)|
|---|---|---|---|
|802.11b, 1 Mbps|—|–97.0|—|
|802.11b, 2 Mbps|—|–94.0|—|



Cont’d on next page


Espressif Systems 31 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


7 RF Characteristics



Table 21 – cont’d from previous page

|Rate|Min<br>(dBm)|Typ<br>(dBm)|Max<br>(dBm)|
|---|---|---|---|
|802.11b, 5.5 Mbps|—|–92.0|—|
|802.11b, 11 Mbps|—|–88.0|—|
|802.11g, 6 Mbps|—|–93.0|—|
|802.11g, 9 Mbps|—|–91.0|—|
|802.11g, 12 Mbps|—|–89.0|—|
|802.11g, 18 Mbps|—|–87.0|—|
|802.11g, 24 Mbps|—|–84.0|—|
|802.11g, 36 Mbps|—|–80.0|—|
|802.11g, 48 Mbps|—|–77.0|—|
|802.11g, 54 Mbps|—|–75.0|—|
|802.11n, HT20, MCS0|—|–92.0|—|
|802.11n, HT20, MCS1|—|–88.0|—|
|802.11n, HT20, MCS2|—|–86.0|—|
|802.11n, HT20, MCS3|—|-83.0|—|
|802.11n, HT20, MCS4|—|–80.0|—|
|802.11n, HT20, MCS5|—|–76.0|—|
|802.11n, HT20, MCS6|—|–74.0|—|
|802.11n, HT20, MCS7|—|–72.0|—|
|802.11n, HT40, MCS0|—|–89.0|—|
|802.11n, HT40, MCS1|—|–85.0|—|
|802.11n, HT40, MCS2|—|–83.0|—|
|802.11n, HT40, MCS3|—|–80.0|—|
|802.11n, HT40, MCS4|—|–76.0|—|
|802.11n, HT40, MCS5|—|–72.0|—|
|802.11n, HT40, MCS6|—|–71.0|—|
|802.11n, HT40, MCS7|—|–69.0|—|



Table 22: Maximum RX Level

|Rate|Min<br>(dBm)|Typ<br>(dBm)|Max<br>(dBm)|
|---|---|---|---|
|802.11b, 1 Mbps|—|5|—|
|802.11b, 11 Mbps|—|5|—|
|802.11g, 6 Mbps|—|0|—|
|802.11g, 54 Mbps|—|-8|—|
|802.11n, HT20, MCS0|—|0|—|
|802.11n, HT20, MCS7|—|-8|—|
|802.11n, HT40, MCS0|—|0|—|
|802.11n, HT40, MCS7|—|-8|—|



Espressif Systems 32 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


7 RF Characteristics


Table 23: RX Adjacent Channel Rejection

|Rate|Min<br>(dB)|Typ<br>(dB)|Max<br>(dB)|
|---|---|---|---|
|802.11b, 11 Mbps|—|35|—|
|802.11g, 6 Mbps|—|27|—|
|802.11g, 54 Mbps|—|13|—|
|802.11n, HT20, MCS0|—|27|—|
|802.11n, HT20, MCS7|—|12|—|
|802.11n, HT40, MCS0|—|16|—|
|802.11n, HT40, MCS7|—|7|—|


###### 7.2 Bluetooth Radio


Table 24: Bluetooth LE RF Characteristics

|Name|Description|
|---|---|
|Center frequency range of operating channel|2402 ~ 2480 MHz|
|RF transmit power range|–12.0 ~ 9.0 dBm|



7.2.1 Receiver – Basic Data Rate


Table 25: Receiver Characteristics – Basic Data Rate







|Parameter|Conditions|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
|Sensitivity @0.1% BER|—|–90|–89|–88|dBm|
|Maximum received signal @0.1% BER|—|0|—|—|dBm|
|Co-channel C/I|—|—|+7|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 1 MHz|—|—|–6|dB|
|Adjacent channel selectivity C/I|F = F0 – 1 MHz|—|—|–6|dB|
|Adjacent channel selectivity C/I|F = F0 + 2 MHz|—|—|–25|dB|
|Adjacent channel selectivity C/I|F = F0 – 2 MHz|—|—|–33|dB|
|Adjacent channel selectivity C/I|F = F0 + 3 MHz|—|—|–25|dB|
|Adjacent channel selectivity C/I|F = F0 – 3 MHz|—|—|–45|dB|
|Out-of-band blocking performance|30 MHz ~ 2000 MHz|–10|—|—|dBm|
|Out-of-band blocking performance|2000 MHz ~ 2400 MHz|–27|—|—|dBm|
|Out-of-band blocking performance|2500 MHz ~ 3000 MHz|–27|—|—|dBm|
|Out-of-band blocking performance|3000 MHz ~ 12.5 GHz|–10|—|—|dBm|
|Intermodulation|—|–36|—|—|dBm|


7.2.2 Transmitter – Basic Data Rate


Espressif Systems 33 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


7 RF Characteristics


Table 26: Transmitter Characteristics – Basic Data Rate







|Parameter<br>RF transmit power*|Conditions<br>—|Min<br>—|Typ<br>0|Max<br>—|Unit<br>dBm|
|---|---|---|---|---|---|
|Gain control step|—|—|3|—|dB|
|RF power control range|—|–12|—|+9|dBm|
|+20 dB bandwidth|—|—|0.9|—|MHz|
|Adjacent channel transmit power|F = F0 ± 2 MHz|—|–55|—|dBm|
|Adjacent channel transmit power|F = F0 ± 3 MHz|—|–55|—|dBm|
|Adjacent channel transmit power|F = F0 ± > 3 MHz|—|–59|—|dBm|
|∆_f_1avg|—|—|—|155|kHz|
|∆_f_2max|—|127|—|—|kHz|
|∆_f_2avg/∆_f_1avg|—|—|0.92|—|—|
|ICFT|—|—|–7|—|kHz|
|Drift rate|—|—|0.7|—|kHz/50_ µ_s|
|Drift (DH1)|—|—|6|—|kHz|
|Drift (DH5)|—|—|6|—|kHz|


      - There are a total of eight power levels from 0 to 7, and the transmit power ranges from –12 dBm


to 9 dBm. When the power level rises by 1, the transmit power increases by 3 dB. Power level 4 is


used by default and the corresponding transmit power is 0 dBm.


7.2.3 Receiver – Enhanced Data Rate


Table 27: Receiver Characteristics – Enhanced Data Rate











|Parameter|Conditions|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
|_π_/4 DQPSK|_π_/4 DQPSK|_π_/4 DQPSK|_π_/4 DQPSK|_π_/4 DQPSK|_π_/4 DQPSK|
|Sensitivity @0.01% BER|—|–90|–89|–88|dBm|
|Maximum received signal @0.01% BER|—|—|0|—|dBm|
|Co-channel C/I|—|—|11|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 1 MHz|—|–7|—|dB|
|Adjacent channel selectivity C/I|F = F0 – 1 MHz|—|–7|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 2 MHz|—|–25|—|dB|
|Adjacent channel selectivity C/I|F = F0 – 2 MHz|—|–35|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 3 MHz|—|–25|—|dB|
|Adjacent channel selectivity C/I|F = F0 – 3 MHz|—|–45|—|dB|
|8DPSK|8DPSK|8DPSK|8DPSK|8DPSK|8DPSK|
|Sensitivity @0.01% BER|—|–84|–83|–82|dBm|
|Maximum received signal @0.01% BER|—|—|–5|—|dBm|
|C/I c-channel|—|—|18|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 1 MHz|—|2|—|dB|
|Adjacent channel selectivity C/I|F = F0 – 1 MHz|—|2|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 2 MHz|—|–25|—|dB|
|Adjacent channel selectivity C/I|F = F0 – 2 MHz|—|–25|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 3 MHz|—|–25|—|dB|


Cont’d on next page



Espressif Systems 34 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


7 RF Characteristics


Table 27 – cont’d from previous page

|Parameter|Conditions|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
||F = F0 – 3 MHz|—|–38|—|dB|



7.2.4 Transmitter – Enhanced Data Rate


Table 28: Transmitter Characteristics – Enhanced Data Rate







|Parameter|Conditions|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
|RF transmit power (see note under Table 26)|—|—|0|—|dBm|
|Gain control step|—|—|3|—|dB|
|RF power control range|—|–12|—|+9|dBm|
|_π_/4 DQPSK max w0|—|—|–0.72|—|kHz|
|_π_/4 DQPSK max wi|—|—|–6|—|kHz|
|_π_/4 DQPSK max |wi + w0||—|—|–7.42|—|kHz|
|8DPSK max w0|—|—|0.7|—|kHz|
|8DPSK max wi|—|—|–9.6|—|kHz|
|8DPSK max |wi + w0||—|—|–10|—|kHz|
|_π_/4 DQPSK modulation accuracy|RMS DEVM|—|4.28|—|%|
|_π_/4 DQPSK modulation accuracy|99% DEVM|—|100|—|%|
|_π_/4 DQPSK modulation accuracy|Peak DEVM|—|13.3|—|%|
|8 DPSK modulation accuracy|RMS DEVM|—|5.8|—|%|
|8 DPSK modulation accuracy|99% DEVM|—|100|—|%|
|8 DPSK modulation accuracy|Peak DEVM|—|14|—|%|
|In-band spurious emissions|F = F0 ± 1 MHz|—|–46|—|dBm|
|In-band spurious emissions|F = F0 ± 2 MHz|—|–44|—|dBm|
|In-band spurious emissions|F = F0 ± 3 MHz|—|–49|—|dBm|
|In-band spurious emissions|F = F0 +/– > 3 MHz|—|—|–53|dBm|
|EDR differential phase coding|—|—|100|—|%|

###### 7.3 Bluetooth LE Radio

7.3.1 Receiver


Table 29: Receiver Characteristics – Bluetooth LE






|Parameter|Conditions|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
|Sensitivity @30.8% PER|—|–94|–93|–92|dBm|
|Maximum received signal @30.8% PER|—|0|—|—|dBm|
|Co-channel C/I|—|—|+10|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 1 MHz|—|–5|—|dB|
|Adjacent channel selectivity C/I|F = F0 – 1 MHz|—|–5|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 2 MHz|—|–25|—|dB|
|Adjacent channel selectivity C/I|F = F0 – 2 MHz|—|–35|—|dB|
|Adjacent channel selectivity C/I|F = F0 + 3 MHz|—|–25|—|dB|



Espressif Systems 35 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


7 RF Characteristics









|Parameter|Conditions|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
||F = F0 – 3 MHz|—|–45|—|dB|
|Out-of-band blocking performance|30 MHz ~ 2000 MHz|–10|—|—|dBm|
|Out-of-band blocking performance|2000<br>MHz<br>~<br>2400<br>MHz|–27|—|—|dBm|
|Out-of-band blocking performance|2500<br>MHz<br>~<br>3000<br>MHz|–27|—|—|dBm|
|Out-of-band blocking performance|3000 MHz ~ 12.5 GHz|–10|—|—|dBm|
|Intermodulation|—|–36|—|—|dBm|


7.3.2 Transmitter


Table 30: Transmitter Characteristics – Bluetooth LE













|Parameter|Conditions|Min|Typ|Max|Unit|
|---|---|---|---|---|---|
|RF transmit power (see note under Table<br>26)|—|—|0|—|dBm|
|Gain control step|—|—|3|—|dB|
|RF power control range|—|–12|—|+9|dBm|
|Adjacent channel transmit power|F = F0 ± 2 MHz|—|–55|—|dBm|
|Adjacent channel transmit power|F = F0 ± 3 MHz|—|–57|—|dBm|
|Adjacent channel transmit power|F = F0 ± > 3 MHz|—|–59|—|dBm|
|∆_f_1avg|—|—|—|265|kHz|
|∆_f_2max|—|210|—|—|kHz|
|∆_f_2avg/∆_f_1avg|—|—|+0.92|—|—|
|ICFT|—|—|–10|—|kHz|
|Drift rate|—|—|0.7|—|kHz/50_ µ_s|
|Drift|—|—|2|—|kHz|


Espressif Systems 36 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


#### 8 Module Schematics

This is the reference design of the module.












|45 R2 0|Col2|Col3|
|---|---|---|
|R2<br>0<br>45|44<br>|43|



































































































































Figure 7: ESP32-WROOM-32E Schematics




|45 R2 0|Col2|
|---|---|
|R2<br>0<br>45|43<br>44|































































































































Figure 8: ESP32-WROOM-32UE Schematics




9 Peripheral Schematics

#### 9 Peripheral Schematics


This is the typical application circuit of the module connected with peripheral components (for example,


power supply, antenna, reset button, JTAG interface, and UART interface).

























































































Figure 9: Peripheral Schematics


_•_ Soldering EPAD Pin 39 to the ground of the base board is not a must. If you choose to solder it, please


apply the correct amount of soldering paste. Too much soldering paste may increase the gap between


the module and the baseboard. As a result, the adhesion between other pins and the baseboard may be


poor.


_•_ To ensure that the power supply to the ESP32 chip is stable during power-up, it is advised to add an RC


delay circuit at the EN pin. The recommended setting for the RC delay circuit is usually R = 10 kΩ and C =


1 _µ_ F. However, specific parameters should be adjusted based on the power-up timing of the module and


the power-up and reset sequence timing of the chip. For ESP32’s power-up and reset sequence timing


diagram, please refer to Section 4.6 _Chip Power-up and Reset_ .


_•_ UART0 is used to download firmware and log output. When using the AT firmware, please note that the


UART GPIO is already configured (refer to _[Hardware Connection](https://docs.espressif.com/projects/esp-at/en/latest/esp32/Get_Started/Hardware_connection.html#esp32)_ ). It is recommended to use the default


configuration.


Espressif Systems 39 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


10 Physical Dimensions

#### 10 Physical Dimensions

###### 10.1 Module Dimensions








|Col1|Col2|Col3|Col4|Col5|Col6|Col7|Col8|Col9|
|---|---|---|---|---|---|---|---|---|
||||||||||
|16.51<br>6.19|||||||||
|16.51<br>6.19|||||||||
|16.51<br>6.19|38x 0.9|7||15.8<br>6<br>38 x Ø0.55|15.8<br>6<br>38 x Ø0.55|15.8<br>6<br>38 x Ø0.55|15.8<br>6<br>38 x Ø0.55||







Figure 10: ESP32-WROOM-32E Physical Dimensions
















|Col1|18±0.15 3.27|Col3|Col4|
|---|---|---|---|
|1.27|~~10.75~~<br>15.65<br>5<br>~~38 x Ø0.55~~<br>05||3.07|
|1.27|Top View<br>~~38~~ ~~x 0.45~~<br>17.<br>~~1.18~~<br>11.43<br>13.|||



Figure 11: ESP32-WROOM-32UE Physical Dimensions


Note:


For information about tape, reel, and product marking, please refer to _[ESP32 Module Packaging Information](https://docs.espressif.com/projects/esp-packaging/en/latest/esp32/00-index/index_module.html)_ .


Espressif Systems 40 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


10 Physical Dimensions

###### 10.2 Dimensions of External Antenna Connector


ESP32-WROOM-32UE uses the first generation external antenna connector as shown in Figure 12 _Dimensions_


_of External Antenna Connector_ . This connector is compatible with the following connectors:


_•_ U.FL Series connector from Hirose


_•_ MHF I connector from I-PEX


_•_ AMC connector from Amphenol


Figure 12: Dimensions of External Antenna Connector


The external antenna used for ESP32-WROOM-32UE during certification testing is the first generation


Espressif Systems 41 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


10 Physical Dimensions


monopole antenna, with material code TFPD05H08750011.


The module does not include an external antenna upon shipment. If needed, select a suitable external


antenna based on the product’s usage environment and performance requirements.


It is recommended to select an antenna that meets the following requirements:


_•_ 2.4 GHz band


_•_ 50 Ω impedance


_•_ The maximum gain does not exceed 2.33 dBi, the gain of the antenna used for certification


_•_ The connector matches the specifications shown in Figure 12 _Dimensions of External Antenna Connector_


Note:


If you use an external antenna of a different type or gain, additional testing, such as EMC, may be required beyond the


existing antenna test reports for Espressif modules. Specific requirements depend on the certification type.


Espressif Systems 42 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


11 PCB Layout Recommendations

#### 11 PCB Layout Recommendations

###### 11.1 PCB Land Pattern


This section provides the following resources for your reference:


_•_ Figures for recommended PCB land patterns with all the dimensions needed for PCB design. See Figure


13 _ESP32-WROOM-32E Recommended PCB Land Pattern_ and Figure 14 _ESP32-WROOM-32UE_


_Recommended PCB Land Pattern_ .


_•_ Source files of recommended PCB land patterns to measure dimensions not covered in Figure 13 and


[Figure 14. You can view the source files for ESP32-WROOM-32E](https://www.espressif.com/sites/default/files/modules-dxf/ESP32-WROOM-32D%2632E%2632SE%2CESP32-SOLO-1%20PCB%20Footprint_0.dxf) [and ESP32-WROOM-32UE](https://www.espressif.com/sites/default/files/modules-dxf/ESP32-WROOM-32UE%20PCB%20Footprint_0.dxf) with


[Autodesk Viewer.](https://viewer.autodesk.com/)


_•_ [3D models of ESP32-WROOM-32E](https://www.espressif.com/sites/default/files/3dmodel/ESP32-WROOM-32E_20210903_0.STEP) [and ESP32-WROOM-32UE. Please make sure that you download the](https://www.espressif.com/sites/default/files/3dmodel/ESP32-WROOM-32UE_20210906_0.STEP)


3D model file in .STEP format (beware that some browsers might add .txt).










|Col1|Col2|Antenna Area|6.19|
|---|---|---|---|
|||||
|||||
|||||
|||||






|Col1|Col2|Col3|Col4|
|---|---|---|---|
|||||
|||||
|||||



Figure 13: ESP32-WROOM-32E Recommended PCB Land Pattern


Espressif Systems 43 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


11 PCB Layout Recommendations














|Col1|Col2|Col3|Col4|Col5|Col6|
|---|---|---|---|---|---|
|||||||
|||||||
|||||||



Figure 14: ESP32-WROOM-32UE Recommended PCB Land Pattern


Espressif Systems 44 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


11 PCB Layout Recommendations

###### 11.2 Module Placement for PCB Design


If module-on-board design is adopted, attention should be paid while positioning the module on the base


board. The interference of the base board on the module’s antenna performance should be minimized.


For details about module placement for PCB design, please refer to _[ESP32 Hardware Design Guidelines](https://espressif.com/documentation/esp32_hardware_design_guidelines_en.pdf)_ 

Section _Positioning a Module on a Base Board_ .


Espressif Systems 45 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


12 Product Handling

#### 12 Product Handling

###### 12.1 Storage Conditions


The products sealed in moisture barrier bags (MBB) should be stored in a non-condensing atmospheric


environment of < 40 °C and 90%RH. The module is rated at the moisture sensitivity level (MSL) of 3.


After unpacking, the module must be soldered within 168 hours with the factory conditions 25 ± 5 °C and 60


%RH. If the above conditions are not met, the module needs to be baked.

###### 12.2 Electrostatic Discharge (ESD)


_•_ Human body model (HBM): ±2000 V

_•_ Charged-device model (CDM): ±500 V

###### 12.3 Reflow Profile



Solder the module in a single reflow.






|Col1|Col2|Col3|Col4|Peak Temp. 235 ~ 250 ℃|
|---|---|---|---|---|
||Preheating<br>150 ~ 200 ℃|zone<br> 60 ~ 120 s||Reﬂow zone <br>!217 ℃  60 ~ 90 s|
||||||
|1 ~ 3 ℃/s<br>Ramp-up zone||||Soldering time<br>> 30 s|











Figure 15: Reflow Profile


Espressif Systems 46 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


12 Product Handling

###### 12.4 Ultrasonic Vibration


Avoid exposing Espressif modules to vibration from ultrasonic equipment, such as ultrasonic welders or


ultrasonic cleaners. This vibration may induce resonance in the in-module crystal and lead to its malfunction or


even failure. As a consequence, the module may stop working or its performance may deteriorate.


Espressif Systems 47 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


_Datasheet Versioning_

#### Datasheet Versioning


















|Datasheet<br>Version|Status|Watermark|Definition|
|---|---|---|---|
|v0.1 ~ v0.5<br>(excluding v0.5)|Draft|Confdential|This datasheet is under development for products<br>in the design stage. Specifcations may change<br>without prior notice.|
|v0.5 ~ v1.0<br>(excluding v1.0)|Preliminary<br>release|Preliminary|This datasheet is actively updated for products in<br>the verifcation stage. Specifcations may change<br>before mass production, and the changes will be<br>documentation in the datasheet’s Revision History.|
|v1.0 and higher|Offcial release|—|This datasheet is publicly released for products in<br>mass production. Specifcations are fnalized, and<br>major changes will be communicated via Product<br>Change Notifcations (PCN).|
|Any version|—|Not<br>Recommended<br>for New Design<br>(NRND)1|This datasheet is updated less frequently for<br>products not recommended for new designs.|
|Any version|—|End of Life<br>(EOL)2|This datasheet is no longer mtained for products<br>that have reached end of life.|



1 Watermark will be added to the datasheet title page only when all the product variants covered by this


datasheet are not recommended for new designs.
2 Watermark will be added to the datasheet title page only when all the product variants covered by this


datasheet have reached end of life.


Espressif Systems 48 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


_Related Documentation and Resources_

#### Related Documentation and Resources

###### Related Documentation


_•_ [ESP32 Series Datasheet](https://espressif.com/documentation/esp32_datasheet_en.pdf) – Specifications of the ESP32 hardware.


_•_ [ESP32 Technical Reference Manual](https://espressif.com/documentation/esp32_technical_reference_manual_en.pdf) – Detailed information on how to use the ESP32 memory and peripherals.


_•_ [ESP32 Hardware Design Guidelines](https://espressif.com/documentation/esp32_hardware_design_guidelines_en.pdf) – Guidelines on how to integrate the ESP32 into your hardware product.


_•_ [ESP32 ECO and Workarounds for Bugs](https://espressif.com/documentation/eco_and_workarounds_for_bugs_in_esp32_en.pdf) – Correction of ESP32 design errors.


_•_ [ESP32 Series SoC Errata](https://espressif.com/sites/default/files/documentation/esp32_errata_en.pdf) – Descriptions of known errors in ESP32 series of SoCs.


_• Certificates_


[https://espressif.com/en/support/documents/certifcatesi](https://espressif.com/en/support/documents/certificates?keys=&field_product_value%5B%5D=ESP32{}-WROOM-32E{}&field_product_value%5B%5D=ESP32{}-WROOM-32UE{})


_• ESP32 Product/Process Change Notifications (PCN)_


[https://espressif.com/en/support/documents/pcns](https://espressif.com/en/support/documents/pcns)


_• ESP32 Advisories_ – Information on security, bugs, compatibility, component reliability.


[https://espressif.com/en/support/documents/advisories](https://espressif.com/en/support/documents/advisories)


_• Documentation Updates and Update Notification Subscription_


[https://espressif.com/en/support/download/documents](https://espressif.com/en/support/download/documents)

###### Developer Zone


_•_ [ESP-IDF Programming Guide for ESP32](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/index.html) – Extensive documentation for the ESP-IDF development framework.


_• ESP-IDF_ and other development frameworks on GitHub.


[https://github.com/espressif](https://github.com/espressif)


_• ESP32 BBS Forum_ – Engineer-to-Engineer (E2E) Community for Espressif products where you can post questions,


share knowledge, explore ideas, and help solve problems with fellow engineers.


[https://esp32.com/](https://esp32.com/)


_• The ESP Journal_ – Best Practices, Articles, and Notes from Espressif folks.


[https://blog.espressif.com/](https://blog.espressif.com/)


_•_ See the tabs _SDKs and Demos_, _Apps_, _Tools_, _AT Firmware_ .


[https://espressif.com/en/support/download/sdks-demos](https://espressif.com/en/support/download/sdks-demos)

###### Products


_• ESP32 Series SoCs_ – Browse through all ESP32 SoCs.


[https://espressif.com/en/products/socs?id=ESP32](https://espressif.com/en/products/socs?id=ESP32)


_• ESP32 Series Modules_ – Browse through all ESP32-based modules.


[https://espressif.com/en/products/modules?id=ESP32](https://espressif.com/en/products/modules?id=ESP32)


_• ESP32 Series DevKits_ – Browse through all ESP32-based devkits.


[https://espressif.com/en/products/devkits?id=ESP32](https://espressif.com/en/products/devkits?id=ESP32)


_• ESP Product Selector_ – Find an Espressif hardware product suitable for your needs by comparing or applying filters.


[https://products.espressif.com/#/product-selector?language=en](https://products.espressif.com/#/product-selector?language=en)

###### Contact Us


_•_ See the tabs _Sales Questions_, _Technical Enquiries_, _Circuit Schematic & PCB Design Review_, _Get Samples_


(Online stores), _Become Our Supplier_, _Comments & Suggestions_ .


                        -                        [https://espressif.com/en/contact](https://espressif.com/en/contact-us/sales-questions) us/sales questions


Espressif Systems 49 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


_Revision History_

#### Revision History







|Date|Version|Release notes|
|---|---|---|
|2025-10-20|v2.0|_•_ Section 2_ Block Diagram_: Added a note about pin mapping between the<br>chip and the in-package fash/PSRAM<br>_•_ Updated Figure 4_ Visualization of Timing Parameters for the Strapping_<br>_Pins_<br>_•_ Added Section 4.6_ Chip Power-up and Reset_<br>_•_ Table 15_ DC Characteristics (3.3 V, 25 °C)_: Added V_IH_nRST_<br>_•_ Added Section 6.5_ Memory Specifcations_<br>_•_ Added Section Datasheet Versioning|
|2025-07-15|v1.9|_•_ Section 10.2_ Dimensions of External Antenna Connector_: Added the ex-<br>ternal antenna information for certifcation.|
|2025-04-14|v1.8|_•_ Section 9_ Peripheral Schematics_: Added a note about UART|
|2024-09|v1.7|_•_ Improved the wording and structure of following sections:<br>– Updated Section ”Strapping Pins” and renamed to 4_ Boot Confgu-_<br>_rations_<br>– Added Chapter 5_ Peripherals_<br>– Updated Table ”Wi-Fi RF Standards” and renamed to Wi-Fi RF Char-<br>acteristics<br>– Added notes about erase cycles and retention time for fash in Table<br>2_ Series Comparison_<br>– Updated note 1 in Chapter 9_ Peripheral Schematics_|
|2023-01-18|v1.6|_•_ Major updates:<br>– Removed contents about hall sensor according to PCN20221202<br>_•_ Other updates:<br>– Added source fles of PCB land patterns and 3D models of the mod-<br>ules in Section 11.1_ PCB Land Pattern_|
|2022-07-20|v1.5|_•_ Added module variants embedded with ESP32-D0WDR2-V3 chip<br>_•_ Added Table 1_ Series Comparison_ and Table 2_ Series Comparison_<br>_•_ Added Figure 4_ Visualization of Timing Parameters for the Strapping Pins_<br>and Table 5_ Description of Timing Parameters for the Strapping Pins_ in<br>Section 4_ Boot Confgurations_<br>_•_ Updated Section 12_ Product Handling_|
|2022-02-22|v1.4|_•_ Added a link to RF certifcates in Section 1.1_ Features_<br>_•_ Fixed a pin name typo in Figure 9_ Peripheral Schematics_|


Cont’d on next page


Espressif Systems 50 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


_Revision History_


Cont’d from previous page







|Date|Version|Release notes|
|---|---|---|
|2021-11-08|v1.3|_•_ Added a 105 °C module variant<br>_•_ Updated Table 13_ Absolute Maximum Ratings_<br>_•_ Updated Table 14_ Recommended Operating Conditions_<br>_•_ Replaced Espressif Product Ordering Information with ESP Product<br>Selector<br>_•_ Updated the description of TWAI in Section 1.1_ Features_<br>_•_ Added a note below Figure 11_ ESP32-WROOM-32UE Physical Dimensions_<br>_•_ Upgraded fgure formatting<br>_•_ Upgraded document formatting|
|2021-02-09|v1.2|_•_ Updated Figure 13_ ESP32-WROOM-32E Recommended PCB Land Pat-_<br>_tern_, Figure 14_ ESP32-WROOM-32UE Recommended PCB Land Pattern_,<br>Figure 10_ ESP32-WROOM-32E Physical Dimensions_, and Figure 11_ ESP32-_<br>_WROOM-32UE Physical Dimensions_<br>_•_ Modifed the note below Figure 15_ Refow Profle_<br>_•_ Updated the trade mark from TWAI™to TWAI®|
|2020-11-02|v1.1|_•_ Updated the table 16_ Current Consumption Depending on RF Modes_<br>_•_ Added a note to EPAD in Section 11.1_ PCB Land Pattern_<br>_•_ Updated the note to RC circuit in Section 9_ Peripheral Schematics_|
|2020-05-29|v1.0|Offcial release|
|2020-05-18|v0.5|Preliminary release|


Espressif Systems 51 ESP32-WROOM-32E & WROOM-32UE Datasheet v2.0
[Submit Documentation Feedback](https://www.espressif.com/en/company/documents/documentation_feedback?docId=4528&sections=&version=2.0)


ww



Disclaimer and Copyright Notice


Information in this document, including URL references, is subject to change without notice.


ALL THIRD PARTY’S INFORMATION IN THIS DOCUMENT IS PROVIDED AS IS WITH NO WARRANTIES TO ITS AUTHENTICITY AND

ACCURACY.


NO WARRANTY IS PROVIDED TO THIS DOCUMENT FOR ITS MERCHANTABILITY, NON-INFRINGEMENT, FITNESS FOR ANY PARTICULAR

PURPOSE, NOR DOES ANY WARRANTY OTHERWISE ARISING OUT OF ANY PROPOSAL, SPECIFICATION OR SAMPLE.


All liability, including liability for infringement of any proprietary rights, relating to use of information in this document is disclaimed. No
licenses express or implied, by estoppel or otherwise, to any intellectual property rights are granted herein.


The Wi-Fi Alliance Member logo is a trademark of the Wi-Fi Alliance. The Bluetooth logo is a registered trademark of Bluetooth SIG.


All trade names, trademarks and registered trademarks mentioned in this document are property of their respective owners, and are
hereby acknowledged.


Copyright © 2025 Espressif Systems (Shanghai) Co., Ltd. All rights reserved.


[w.espressif.comww](https://www.espressif.com/)


