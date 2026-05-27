architecture sample_arch of template is
  component xillybus
    port (
      PS_CLK : IN std_logic;
      PS_PORB : IN std_logic;
      PS_SRSTB : IN std_logic;
      clk_100 : IN std_logic;
      otg_oc : IN std_logic;
      DDR_Addr : INOUT std_logic_vector(14 DOWNTO 0);
      DDR_BankAddr : INOUT std_logic_vector(2 DOWNTO 0);
      DDR_CAS_n : INOUT std_logic;
      DDR_CKE : INOUT std_logic;
      DDR_CS_n : INOUT std_logic;
      DDR_Clk : INOUT std_logic;
      DDR_Clk_n : INOUT std_logic;
      DDR_DM : INOUT std_logic_vector(3 DOWNTO 0);
      DDR_DQ : INOUT std_logic_vector(31 DOWNTO 0);
      DDR_DQS : INOUT std_logic_vector(3 DOWNTO 0);
      DDR_DQS_n : INOUT std_logic_vector(3 DOWNTO 0);
      DDR_DRSTB : INOUT std_logic;
      DDR_ODT : INOUT std_logic;
      DDR_RAS_n : INOUT std_logic;
      DDR_VRN : INOUT std_logic;
      DDR_VRP : INOUT std_logic;
      MIO : INOUT std_logic_vector(53 DOWNTO 0);
      PS_GPIO : INOUT std_logic_vector(55 DOWNTO 0);
      DDR_WEB : OUT std_logic;
      GPIO_LED : OUT std_logic_vector(3 DOWNTO 0);
      bus_clk : OUT std_logic;
      quiesce : OUT std_logic;
      vga4_blue : OUT std_logic_vector(3 DOWNTO 0);
      vga4_green : OUT std_logic_vector(3 DOWNTO 0);
      vga4_red : OUT std_logic_vector(3 DOWNTO 0);
      vga_hsync : OUT std_logic;
      vga_vsync : OUT std_logic;
      user_r_mem_32_rden : OUT std_logic;
      user_r_mem_32_empty : IN std_logic;
      user_r_mem_32_data : IN std_logic_vector(31 DOWNTO 0);
      user_r_mem_32_eof : IN std_logic;
      user_r_mem_32_open : OUT std_logic;
      user_w_mem_32_wren : OUT std_logic;
      user_w_mem_32_full : IN std_logic;
      user_w_mem_32_data : OUT std_logic_vector(31 DOWNTO 0);
      user_w_mem_32_open : OUT std_logic;
      user_mem_32_addr : OUT std_logic_vector(15 DOWNTO 0);
      user_mem_32_addr_update : OUT std_logic;
      user_r_read_32_rden : OUT std_logic;
      user_r_read_32_empty : IN std_logic;
      user_r_read_32_data : IN std_logic_vector(31 DOWNTO 0);
      user_r_read_32_eof : IN std_logic;
      user_r_read_32_open : OUT std_logic;
      user_r_read_32_2_rden : OUT std_logic;
      user_r_read_32_2_empty : IN std_logic;
      user_r_read_32_2_data : IN std_logic_vector(31 DOWNTO 0);
      user_r_read_32_2_eof : IN std_logic;
      user_r_read_32_2_open : OUT std_logic;
      user_r_read_8_rden : OUT std_logic;
      user_r_read_8_empty : IN std_logic;
      user_r_read_8_data : IN std_logic_vector(7 DOWNTO 0);
      user_r_read_8_eof : IN std_logic;
      user_r_read_8_open : OUT std_logic;
      user_r_smb_rden : OUT std_logic;
      user_r_smb_empty : IN std_logic;
      user_r_smb_data : IN std_logic_vector(7 DOWNTO 0);
      user_r_smb_eof : IN std_logic;
      user_r_smb_open : OUT std_logic;
      user_w_smb_wren : OUT std_logic;
      user_w_smb_full : IN std_logic;
      user_w_smb_data : OUT std_logic_vector(7 DOWNTO 0);
      user_w_smb_open : OUT std_logic;
      user_w_write_32_wren : OUT std_logic;
      user_w_write_32_full : IN std_logic;
      user_w_write_32_data : OUT std_logic_vector(31 DOWNTO 0);
      user_w_write_32_open : OUT std_logic;
      user_w_write_32_2_wren : OUT std_logic;
      user_w_write_32_2_full : IN std_logic;
      user_w_write_32_2_data : OUT std_logic_vector(31 DOWNTO 0);
      user_w_write_32_2_open : OUT std_logic;
      user_w_write_8_wren : OUT std_logic;
      user_w_write_8_full : IN std_logic;
      user_w_write_8_data : OUT std_logic_vector(7 DOWNTO 0);
      user_w_write_8_open : OUT std_logic;
      user_clk : OUT std_logic;
      user_wren : OUT std_logic;
      user_rden : OUT std_logic;
      user_wstrb : OUT std_logic_vector(3 DOWNTO 0);
      user_addr : OUT std_logic_vector(31 DOWNTO 0);
      user_rd_data : IN std_logic_vector(31 DOWNTO 0);
      user_wr_data : OUT std_logic_vector(31 DOWNTO 0);
      user_irq : IN std_logic);
  end component;

  signal bus_clk :  std_logic;
  signal quiesce : std_logic;
  signal user_r_mem_32_rden :  std_logic;
  signal user_r_mem_32_empty :  std_logic;
  signal user_r_mem_32_data :  std_logic_vector(31 DOWNTO 0);
  signal user_r_mem_32_eof :  std_logic;
  signal user_r_mem_32_open :  std_logic;
  signal user_w_mem_32_wren :  std_logic;
  signal user_w_mem_32_full :  std_logic;
  signal user_w_mem_32_data :  std_logic_vector(31 DOWNTO 0);
  signal user_w_mem_32_open :  std_logic;
  signal user_mem_32_addr :  std_logic_vector(15 DOWNTO 0);
  signal user_mem_32_addr_update :  std_logic;
  signal user_r_read_32_rden :  std_logic;
  signal user_r_read_32_empty :  std_logic;
  signal user_r_read_32_data :  std_logic_vector(31 DOWNTO 0);
  signal user_r_read_32_eof :  std_logic;
  signal user_r_read_32_open :  std_logic;
  signal user_r_read_32_2_rden :  std_logic;
  signal user_r_read_32_2_empty :  std_logic;
  signal user_r_read_32_2_data :  std_logic_vector(31 DOWNTO 0);
  signal user_r_read_32_2_eof :  std_logic;
  signal user_r_read_32_2_open :  std_logic;
  signal user_r_read_8_rden :  std_logic;
  signal user_r_read_8_empty :  std_logic;
  signal user_r_read_8_data :  std_logic_vector(7 DOWNTO 0);
  signal user_r_read_8_eof :  std_logic;
  signal user_r_read_8_open :  std_logic;
  signal user_r_smb_rden :  std_logic;
  signal user_r_smb_empty :  std_logic;
  signal user_r_smb_data :  std_logic_vector(7 DOWNTO 0);
  signal user_r_smb_eof :  std_logic;
  signal user_r_smb_open :  std_logic;
  signal user_w_smb_wren :  std_logic;
  signal user_w_smb_full :  std_logic;
  signal user_w_smb_data :  std_logic_vector(7 DOWNTO 0);
  signal user_w_smb_open :  std_logic;
  signal user_w_write_32_wren :  std_logic;
  signal user_w_write_32_full :  std_logic;
  signal user_w_write_32_data :  std_logic_vector(31 DOWNTO 0);
  signal user_w_write_32_open :  std_logic;
  signal user_w_write_32_2_wren :  std_logic;
  signal user_w_write_32_2_full :  std_logic;
  signal user_w_write_32_2_data :  std_logic_vector(31 DOWNTO 0);
  signal user_w_write_32_2_open :  std_logic;
  signal user_w_write_8_wren :  std_logic;
  signal user_w_write_8_full :  std_logic;
  signal user_w_write_8_data :  std_logic_vector(7 DOWNTO 0);
  signal user_w_write_8_open :  std_logic;
  signal user_clk :  std_logic;
  signal user_wren :  std_logic;
  signal user_rden :  std_logic;
  signal user_wstrb :  std_logic_vector(3 DOWNTO 0);
  signal user_addr :  std_logic_vector(31 DOWNTO 0);
  signal user_rd_data :  std_logic_vector(31 DOWNTO 0);
  signal user_wr_data :  std_logic_vector(31 DOWNTO 0);
  signal user_irq :  std_logic;

begin
  xillybus_ins : xillybus
    port map (
      -- Ports related to /dev/xillybus_mem_32
      -- FPGA to CPU signals:
      user_r_mem_32_rden => user_r_mem_32_rden,
      user_r_mem_32_empty => user_r_mem_32_empty,
      user_r_mem_32_data => user_r_mem_32_data,
      user_r_mem_32_eof => user_r_mem_32_eof,
      user_r_mem_32_open => user_r_mem_32_open,
      -- CPU to FPGA signals:
      user_w_mem_32_wren => user_w_mem_32_wren,
      user_w_mem_32_full => user_w_mem_32_full,
      user_w_mem_32_data => user_w_mem_32_data,
      user_w_mem_32_open => user_w_mem_32_open,
      -- Address signals:
      user_mem_32_addr => user_mem_32_addr,
      user_mem_32_addr_update => user_mem_32_addr_update,

      -- Ports related to /dev/xillybus_read_32
      -- FPGA to CPU signals:
      user_r_read_32_rden => user_r_read_32_rden,
      user_r_read_32_empty => user_r_read_32_empty,
      user_r_read_32_data => user_r_read_32_data,
      user_r_read_32_eof => user_r_read_32_eof,
      user_r_read_32_open => user_r_read_32_open,

      -- Ports related to /dev/xillybus_read_32_2
      -- FPGA to CPU signals:
      user_r_read_32_2_rden => user_r_read_32_2_rden,
      user_r_read_32_2_empty => user_r_read_32_2_empty,
      user_r_read_32_2_data => user_r_read_32_2_data,
      user_r_read_32_2_eof => user_r_read_32_2_eof,
      user_r_read_32_2_open => user_r_read_32_2_open,

      -- Ports related to /dev/xillybus_read_8
      -- FPGA to CPU signals:
      user_r_read_8_rden => user_r_read_8_rden,
      user_r_read_8_empty => user_r_read_8_empty,
      user_r_read_8_data => user_r_read_8_data,
      user_r_read_8_eof => user_r_read_8_eof,
      user_r_read_8_open => user_r_read_8_open,

      -- Ports related to /dev/xillybus_smb
      -- FPGA to CPU signals:
      user_r_smb_rden => user_r_smb_rden,
      user_r_smb_empty => user_r_smb_empty,
      user_r_smb_data => user_r_smb_data,
      user_r_smb_eof => user_r_smb_eof,
      user_r_smb_open => user_r_smb_open,
      -- CPU to FPGA signals:
      user_w_smb_wren => user_w_smb_wren,
      user_w_smb_full => user_w_smb_full,
      user_w_smb_data => user_w_smb_data,
      user_w_smb_open => user_w_smb_open,

      -- Ports related to /dev/xillybus_write_32
      -- CPU to FPGA signals:
      user_w_write_32_wren => user_w_write_32_wren,
      user_w_write_32_full => user_w_write_32_full,
      user_w_write_32_data => user_w_write_32_data,
      user_w_write_32_open => user_w_write_32_open,

      -- Ports related to /dev/xillybus_write_32_2
      -- CPU to FPGA signals:
      user_w_write_32_2_wren => user_w_write_32_2_wren,
      user_w_write_32_2_full => user_w_write_32_2_full,
      user_w_write_32_2_data => user_w_write_32_2_data,
      user_w_write_32_2_open => user_w_write_32_2_open,

      -- Ports related to /dev/xillybus_write_8
      -- CPU to FPGA signals:
      user_w_write_8_wren => user_w_write_8_wren,
      user_w_write_8_full => user_w_write_8_full,
      user_w_write_8_data => user_w_write_8_data,
      user_w_write_8_open => user_w_write_8_open,

      -- Ports related to Xillybus Lite
      user_clk => user_clk,
      user_wren => user_wren,
      user_rden => user_rden,
      user_wstrb => user_wstrb,
      user_addr => user_addr,
      user_rd_data => user_rd_data,
      user_wr_data => user_wr_data,
      user_irq => user_irq,

      -- General signals
      PS_CLK => PS_CLK,
      PS_PORB => PS_PORB,
      PS_SRSTB => PS_SRSTB,
      clk_100 => clk_100,
      otg_oc => otg_oc,
      DDR_Addr => DDR_Addr,
      DDR_BankAddr => DDR_BankAddr,
      DDR_CAS_n => DDR_CAS_n,
      DDR_CKE => DDR_CKE,
      DDR_CS_n => DDR_CS_n,
      DDR_Clk => DDR_Clk,
      DDR_Clk_n => DDR_Clk_n,
      DDR_DM => DDR_DM,
      DDR_DQ => DDR_DQ,
      DDR_DQS => DDR_DQS,
      DDR_DQS_n => DDR_DQS_n,
      DDR_DRSTB => DDR_DRSTB,
      DDR_ODT => DDR_ODT,
      DDR_RAS_n => DDR_RAS_n,
      DDR_VRN => DDR_VRN,
      DDR_VRP => DDR_VRP,
      MIO => MIO,
      PS_GPIO => PS_GPIO,
      DDR_WEB => DDR_WEB,
      GPIO_LED => GPIO_LED,
      bus_clk => bus_clk,
      quiesce => quiesce,
      vga4_blue => vga4_blue,
      vga4_green => vga4_green,
      vga4_red => vga4_red,
      vga_hsync => vga_hsync,
      vga_vsync => vga_vsync
  );
end sample_arch;
