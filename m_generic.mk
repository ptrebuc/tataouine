# generic verbose management
# To put more focus on warnings, be less verbose as default
# Use 'make V=1' to see the full commands

ifeq ("$(origin V)", "command line")
  KBUILD_VERBOSE = $(V)
  VERBOSE = $(V)
endif
ifndef KBUILD_VERBOSE
  KBUILD_VERBOSE = 0
endif

ifeq ($(KBUILD_VERBOSE),1)
  quiet =
  Q =
else
  quiet=quiet_
  Q = @
  VERBOSE = 0
endif

# If the user is running make -s (silent mode), suppress echoing of
# commands

ifneq ($(findstring s,$(filter-out --%,$(MAKEFLAGS))),)
  quiet=silent_
  tools_silent=s
endif

# here, we update the drivers and libs inclusion cflags
# to be relative to the current compoent build directory.
# For this, we update the CFLAGS value, replacing the
# @PROJFILES@ with the local value of $(PROJ_FILES)
#
LIBS_CFLAGS := $(subst @PROJFILES@,$(PROJ_FILES),$(LIBS_CFLAGS))
DRIVERS_CFLAGS := $(subst @PROJFILES@,$(PROJ_FILES),$(DRIVERS_CFLAGS))
APPS_CFLAGS := $(subst @PROJFILES@,$(PROJ_FILES),$(APPS_CFLAGS))



# disable directory entering/leaving printout
#MAKEFLAGS += --no-print-directory

export quiet Q KBUILD_VERBOSE MAKE MAKEFLAGS

# including Kbuild related tools for silent CC
include $(PROJ_FILES)/tools/Kbuild.include
include $(PROJ_FILES)/m_build.mk

# generic CFLAGS
CFLAGS += -I$(PROJ_FILES)/include/generated
CFLAGS += $(DEBUG_CFLAGS)

# GENERIC TARGETS
default: all

.PHONY: clean distclean

clean:
	$(call cmd,clean)

distclean: clean
	$(call cmd,distclean)

$(BUILD_DIR):
	$(call cmd,mkdir)

######### Key generation target
# Generate keys
genkeys:
	@# We need ec_utils to generate our keys. Build it
	@make -C externals/;
	@echo $(AUTH_TOKEN_MAX_PIN)  >  tmp_gen_keys_file
	@echo $(AUTH_TOKEN_MAX_SC)   >> tmp_gen_keys_file
	@echo $(DFU_TOKEN_MAX_PIN)   >> tmp_gen_keys_file
	@echo $(DFU_TOKEN_MAX_SC)    >> tmp_gen_keys_file
ifeq ("$(USE_SIG_TOKEN)","USE_SIG_TOKEN")
	@echo $(SIG_TOKEN_MAX_PIN)   >> tmp_gen_keys_file
	@echo $(SIG_TOKEN_MAX_SC)    >> tmp_gen_keys_file
endif
	@echo $(AUTH_TOKEN_PET_PIN)  >> tmp_gen_keys_file
	@echo $(AUTH_TOKEN_PET_NAME) >> tmp_gen_keys_file
	@echo $(DFU_TOKEN_PET_PIN)   >> tmp_gen_keys_file
	@echo $(DFU_TOKEN_PET_NAME)  >> tmp_gen_keys_file
ifeq ("$(USE_SIG_TOKEN)","USE_SIG_TOKEN")
	@echo $(SIG_TOKEN_PET_PIN)   >> tmp_gen_keys_file
	@echo $(SIG_TOKEN_PET_NAME)  >> tmp_gen_keys_file
else
	@echo $(LOCAL_PASSWORD)      >> tmp_gen_keys_file
endif
	@echo $(AUTH_TOKEN_USER_PIN) >> tmp_gen_keys_file
	@echo $(DFU_TOKEN_USER_PIN)  >> tmp_gen_keys_file
ifeq ("$(CONFIG_USE_SIG_TOKEN_BOOL)","y")
	@echo $(SIG_TOKEN_USER_PIN)  >> tmp_gen_keys_file
endif
	@$(GENKEYS) $(KEYS_DIR) $(EC_UTILS) $(ECC_CURVENAME) $(USE_SIG_TOKEN) < tmp_gen_keys_file
	@rm -f tmp_gen_keys_file

######### Firmware signature targets
# Sign the firmwares with user interactions
define sign_interactive_each_fn =
sign_interactive_each_fn_$(1):
	@if [ "$(3)" = "" ]; then \
		echo "\033[1;41m Error: you did not provide a firmware version, which is mandatory. Please provide it with 'version=XX'.\033[1;m"; false; \
	fi
	@$(OBJCOPY) --only-section=.*text --only-section=.*got -O binary $(BUILD_DIR)/$(APP_NAME)/$(1).elf $(BUILD_DIR)/$(APP_NAME)/$(1).bin
	@# Get the firmware type from the ELF file
	@FIRMWARE_TYPE=$$$$(cat $(BUILD_DIR)/$(APP_NAME)/layout.ld | grep `$(OBJDUMP) -h $(BUILD_DIR)/$(APP_NAME)/$(1).elf |grep "\.isr_vector" | cut -d " " -f9` | sed 's/_.*//g' | sed 's/ //g'); \
	if [ "$(2)" != "" ]; then \
		FIRMWARE_MAGIC=$(2); \
	else \
		FIRMWARE_MAGIC=123456789; \
	fi; \
	if [ "$(4)" != "" ]; then \
		FIRMWARE_CHUNK_SIZE=$(4); \
	else \
		FIRMWARE_CHUNK_SIZE=16384; \
	fi; \
	echo "++++++++++ Interactive signing $(1), magic=$$$$FIRMWARE_MAGIC, version=$(3), chunk size=$$$$FIRMWARE_CHUNK_SIZE +++++++++++++++"; \
	$(SIGNFIRMWARE) $(KEYS_DIR) $(BUILD_DIR)/$(APP_NAME)/$(1).bin $$$$FIRMWARE_MAGIC $$$$FIRMWARE_TYPE $(3) $$$$FIRMWARE_CHUNK_SIZE
endef

define sign_interactive_fn =
	$(eval FIRM_TO_SIGN = $(subst :, ,$(1)))
	$(eval FIRM_MAGIC = $(2))
	$(eval FIRM_VERSION = $(3))
	$(eval FIRM_CHUNK_SIZE = $(4))
	$(foreach FIRM,$(FIRM_TO_SIGN), \
		$(eval $(call sign_interactive_each_fn,$(FIRM),$(FIRM_MAGIC),$(FIRM_VERSION),$(FIRM_CHUNK_SIZE))) \
	)
endef

define all_sign_interactive_rules_fn =
	$(eval FIRM_TO_SIGN = $(subst :, ,$(1)))
	$(foreach FIRM,$(FIRM_TO_SIGN), \
		$(eval SIGN_INTERACTIVE_RULES += sign_interactive_each_fn_$(FIRM)) \
	)
	$(SIGN_INTERACTIVE_RULES)
endef

sign_interactive_check:
	@if [ "$(tosign)" = "" ]; then \
		echo "Error: 'sign_interactive' rule expects as argument the firmware list to sign: 'tosign=fw1:fw2:dfu1'"; \
	fi;:

$(eval $(call sign_interactive_fn,$(tosign),$(magic),$(version),$(chunksize)))
sign_interactive: sign_interactive_check $(call all_sign_interactive_rules_fn, $(tosign))

# Sign the firmwares with no user interactions
define sign_each_fn =
sign_each_fn_$(1):
	@if [ "$(3)" = "" ]; then \
		echo "\033[1;41m Error: you did not provide a firmware version, which is mandatory. Please provide it with 'version=XX'.\033[1;m"; false; \
	fi;
	@# Clean stuff
	@rm -f tmp_firmware_sig_file tmp_firmware_sig_log;
	@$(OBJCOPY) --only-section=.*text --only-section=.*got -O binary $(BUILD_DIR)/$(APP_NAME)/$(1).elf $(BUILD_DIR)/$(APP_NAME)/$(1).bin
ifeq ("$(USE_SIG_TOKEN)","USE_SIG_TOKEN")
	@# First we check the PET name
	@echo $(SIG_TOKEN_PET_PIN) >  tmp_firmware_sig_file
	@echo "n"                  >> tmp_firmware_sig_file
	@# Get the firmware type from the ELF file
	@FIRMWARE_TYPE=$$$$(cat $(BUILD_DIR)/$(APP_NAME)/layout.ld | grep `$(OBJDUMP) -h $(BUILD_DIR)/$(APP_NAME)/$(1).elf | grep "\.isr_vector" | cut -d " " -f9` | sed 's/_.*//g' | sed 's/ //g'); \
	if [ "$(2)" != "" ]; then \
		FIRMWARE_MAGIC=$(2); \
	else \
		FIRMWARE_MAGIC=123456789; \
	fi; \
	if [ "$(4)" != "" ]; then \
		FIRMWARE_CHUNK_SIZE=$(4); \
	else \
		FIRMWARE_CHUNK_SIZE=16384; \
	fi; \
	(($(SIGNFIRMWARE) $(KEYS_DIR) $(BUILD_DIR)/$(APP_NAME)/$(1).bin $$$$FIRMWARE_MAGIC $$$$FIRMWARE_TYPE $(3) $$$$FIRMWARE_CHUNK_SIZE < tmp_firmware_sig_file) 1> tmp_firmware_sig_log) | true
	@# Check for error
	@CHECK_ERROR=$$$$(cat tmp_firmware_sig_log | grep -i "Error"); \
	if [ "$$$$CHECK_ERROR" != "" ]; then \
		cat tmp_firmware_sig_log; \
		rm -f tmp_firmware_sig_file tmp_firmware_sig_log; \
		false; \
	fi
	@# Check the PET name
	@PET_NAME=$$$$(cat tmp_firmware_sig_log | grep "The PET name for the SIG token is " | sed "s/The PET name for the SIG token is '//g" | sed "s/', is it correct?.*//g"); \
	if [ "$$$$PET_NAME" != $(SIG_TOKEN_PET_NAME) ]; then \
		echo "\033[1;41m Sorry, PET name mismatch ('$$$$PET_NAME' != '$(SIG_TOKEN_PET_NAME)') for the SIG token.\033[1;m"; \
		echo "This can either be *dangerous* or due to an after production modification of the PET name! Please fall back to the interactive signature!"; \
		rm -f tmp_firmware_sig_file tmp_firmware_sig_log; \
		false; \
	fi
	@# If the PET name is OK, go on
	@echo $(SIG_TOKEN_PET_PIN) >  tmp_firmware_sig_file
	@echo "y"                  >> tmp_firmware_sig_file
	@echo $(SIG_TOKEN_USER_PIN)>> tmp_firmware_sig_file
else
	@echo $(LOCAL_PASSWORD)    > tmp_firmware_sig_file
endif
	@FIRMWARE_TYPE=$$$$(cat $(BUILD_DIR)/$(APP_NAME)/layout.ld | grep `$(OBJDUMP) -h $(BUILD_DIR)/$(APP_NAME)/$(1).elf | grep "\.isr_vector" | cut -d " " -f9` | sed 's/_.*//g' | sed 's/ //g'); \
	if [ "$(2)" != "" ]; then \
		FIRMWARE_MAGIC=$(2); \
	else \
		FIRMWARE_MAGIC=123456789; \
	fi; \
	if [ "$(4)" != "" ]; then \
		FIRMWARE_CHUNK_SIZE=$(4); \
	else \
		FIRMWARE_CHUNK_SIZE=16384; \
	fi; \
	echo "++++++++++ Automatic signing $(1), magic=$$$$FIRMWARE_MAGIC, version=$(3), chunk size=$$$$FIRMWARE_CHUNK_SIZE +++++++++++++++"; \
	$(SIGNFIRMWARE) $(KEYS_DIR) $(BUILD_DIR)/$(APP_NAME)/$(1).bin $$$$FIRMWARE_MAGIC $$$$FIRMWARE_TYPE $(3) $$$$FIRMWARE_CHUNK_SIZE < tmp_firmware_sig_file
	@rm -f tmp_firmware_sig_file tmp_firmware_sig_log
endef

define sign_fn =
	$(eval FIRM_TO_SIGN = $(subst :, ,$(1)))
	$(eval FIRM_MAGIC = $(2))
	$(eval FIRM_VERSION = $(3))
	$(eval FIRM_CHUNK_SIZE = $(4))
	$(foreach FIRM,$(FIRM_TO_SIGN), \
  		$(eval $(call sign_each_fn,$(FIRM),$(FIRM_MAGIC),$(FIRM_VERSION),$(FIRM_CHUNK_SIZE))) \
	)
endef

define all_sign_rules_fn =
	$(eval FIRM_TO_SIGN = $(subst :, ,$(1)))
	$(foreach FIRM,$(FIRM_TO_SIGN), \
		$(eval SIGN_RULES += sign_each_fn_$(FIRM)) \
	)
	$(SIGN_RULES)
endef

sign_check:
	@if [ "$(tosign)" = "" ]; then \
		echo "Error: 'sign' rule expects as argument the firmware list to sign: 'tosign=fw1:fw2:dfu1'"; \
	fi;

$(eval $(call sign_fn,$(tosign),$(magic),$(version),$(chunksize)))
#sign: sign_check $(call all_sign_rules_fn, $(tosign))


######### Firmware verification targets
# Only print the verification information *without* decrypting the file
define verify_info_each_fn =
verify_info_each_fn_$(1):
	@echo "++++++++++ Info on $(1) ++++++++++++++++++++++++++++++"
	@$(VERIFYFIRMWARE) $(KEYS_DIR) $(BUILD_DIR)/$(APP_NAME)/$(1).bin.signed only_info
endef

define verify_info_fn =
	$(eval FIRM_TO_VERIFY = $(subst :, ,$(1)))
	$(foreach FIRM,$(FIRM_TO_VERIFY), \
  		$(eval $(call verify_info_each_fn,$(FIRM))) \
	)

endef

define all_verify_info_rules_fn =
	$(eval FIRM_TO_VERIFY = $(subst :, ,$(1)))
	$(foreach FIRM,$(FIRM_TO_VERIFY), \
		$(eval VERIFY_INFO_RULES += verify_info_each_fn_$(FIRM)) \
	)
	$(VERIFY_INFO_RULES)
endef

$(eval $(call verify_info_fn,$(toverify)))
verify_info: $(call all_verify_info_rules_fn, $(toverify))

# Verify the firmwares with user interactions
define verify_interactive_each_fn =
verify_interactive_each_fn_$(1):
	@echo "++++++++++ Automatic verification $(1) +++++++++++++++"
	@$(VERIFYFIRMWARE) $(KEYS_DIR) $(BUILD_DIR)/$(APP_NAME)/$(1).bin.signed
endef

define verify_interactive_fn =
	$(eval FIRM_TO_VERIFY = $(subst :, ,$(1)))
	$(foreach FIRM,$(FIRM_TO_VERIFY), \
  		$(eval $(call verify_interactive_each_fn,$(FIRM))) \
	)

endef

define all_verify_interactive_rules_fn =
	$(eval FIRM_TO_VERIFY = $(subst :, ,$(1)))
	$(foreach FIRM,$(FIRM_TO_VERIFY), \
		$(eval VERIFY_INTERACTIVE_RULES += verify_interactive_each_fn_$(FIRM)) \
	)
	$(VERIFY_INTERACTIVE_RULES)
endef

verify_interactive_check:
	@if [ "$(toverify)" = "" ]; then \
		echo "Error: 'verify_interactive' rule expects as argument the firmware list to verify: 'toverify=fw1:fw2:dfu1'"; \
	fi;

$(eval $(call verify_interactive_fn,$(toverify)))
verify_interactive: verify_interactive_check $(call all_verify_interactive_rules_fn, $(toverify))


# Verify the firmwares without user interactions
define verify_each_fn =
verify_each_fn_$(1):
	@echo "++++++++++ Interactive verification $(1) +++++++++++++++"
	@# Clean stuff
	@rm -f tmp_firmware_verif_file tmp_firmware_verif_log;
	@# First we check the PET name
	@echo $(DFU_TOKEN_PET_PIN) >  tmp_firmware_verif_file
	@echo "n"                  >> tmp_firmware_verif_file
	@(($(VERIFYFIRMWARE) $(KEYS_DIR) $(BUILD_DIR)/$(APP_NAME)/$(1).bin.signed < tmp_firmware_verif_file) 1> tmp_firmware_verif_log) | true
	@# Check signature
	@CHECK_SIG=$$$$(cat tmp_firmware_verif_log | grep "bad signature"); \
	if [ "$$$$CHECK_SIG" != "" ]; then \
		echo "\033[1;41m Error: bad signature for $(1).bin.signed\033[1;m"; \
		rm -f tmp_firmware_verif_file tmp_firmware_verif_log; \
		false; \
	fi
	@# Check for error
	@CHECK_ERROR=$$$$(cat tmp_firmware_verif_log | grep -i "Error"); \
	if [ "$$$$CHECK_ERROR" != "" ]; then \
		cat tmp_firmware_verif_log; \
		rm -f tmp_firmware_verif_file tmp_firmware_verif_log; \
		false; \
	fi
	@# Check the PET name
	@PET_NAME=$$$$(cat tmp_firmware_verif_log | grep "The PET name for the DFU token is " | sed "s/The PET name for the DFU token is '//g" | sed "s/', is it correct?.*//g"); \
	if [ "$$$$PET_NAME" != $(DFU_TOKEN_PET_NAME) ]; then \
		echo "\033[1;41m Sorry, PET name mismatch ('$$$$PET_NAME' != '$(DFU_TOKEN_PET_NAME)') for the DFU token.\033[1;m"; \
		echo "This can either be *dangerous* or due to an after production modification of the PET name! Please fall back to the interactive verification!"; \
		rm -f tmp_firmware_verif_file tmp_firmware_verif_log; \
		false; \
	fi
	@# If the PET name is OK, go on
	@echo $(DFU_TOKEN_PET_PIN) >  tmp_firmware_verif_file
	@echo "y"                  >> tmp_firmware_verif_file
	@echo $(DFU_TOKEN_USER_PIN)>> tmp_firmware_verif_file
	@$(VERIFYFIRMWARE) $(KEYS_DIR) $(BUILD_DIR)/$(APP_NAME)/$(1).bin.signed < tmp_firmware_verif_file
	@rm -f tmp_firmware_verif_file tmp_firmware_verif_log
endef

define verify_fn =
	$(eval FIRM_TO_VERIFY = $(subst :, ,$(1)))
	$(foreach FIRM,$(FIRM_TO_VERIFY), \
  		$(eval $(call verify_each_fn,$(FIRM))) \
	)
endef

define all_verify_rules_fn =
	$(eval FIRM_TO_VERIFY = $(subst :, ,$(1)))
	$(foreach FIRM,$(FIRM_TO_VERIFY), \
		$(eval VERIFY_RULES += verify_each_fn_$(FIRM)) \
	)
	$(VERIFY_RULES)
endef

verify_check:
	@if [ "$(toverify)" = "" ]; then \
		echo "Error: 'verify' rule expects as argument the firmware list to verify: 'toverify=fw1:fw2:dfu1'"; \
	fi;

$(eval $(call verify_fn,$(toverify)))
verify: verify_check $(call all_verify_rules_fn, $(toverify))

ifeq (y,$(USE_LLVM))
sanitize:
	scan-build --use-cc=$(CC) --analyzer-target=thumbv7m-none-eabi --use-analyzer=$(CLANG_PATH) -enable-checker alpha.security.ArrayBoundV2 -enable-checker alpha.security.ReturnPtrRange -enable-checker alpha.core.CastToStruct -enable-checker alpha.core.DynamicTypeChecker -enable-checker alpha.core.FixedAddr -enable-checker alpha.core.IdenticalExpr -enable-checker alpha.core.PointerArithm -enable-checker alpha.core.PointerSub -enable-checker alpha.core.SizeofPtr -enable-checker alpha.core.TestAfterDivZero -enable-checker alpha.deadcode.UnreachableCode -o $(APP_BUILD_DIR)/scan make
endif

