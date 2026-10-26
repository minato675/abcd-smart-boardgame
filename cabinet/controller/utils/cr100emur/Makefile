CC ?= cc
CXX ?= c++
AR ?= ar
INSTALL ?= install
PYTHON ?= $(abspath ../../.venv/bin/python)

VERSION := 0.2.0
ABI_VERSION := 0
BUILD_DIR := build
PREFIX ?= /usr/local
LIBDIR ?= $(PREFIX)/lib
INCLUDEDIR ?= $(PREFIX)/include
BINDIR ?= $(PREFIX)/bin
UDEVDIR ?= /etc/udev/rules.d

CPPFLAGS += -Iinclude -D_DEFAULT_SOURCE -D_XOPEN_SOURCE=700
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -fPIC -Wall -Wextra -Wpedantic -Werror
CXXFLAGS ?= -O2 -g
CXXFLAGS += -std=c++17 -Wall -Wextra -Wpedantic -Werror
LDFLAGS ?=
THREAD_FLAGS ?= -pthread

LIB_OBJECT := $(BUILD_DIR)/cr100emur.o
STATIC_LIB := $(BUILD_DIR)/libcr100emur.a
SHARED_REAL := $(BUILD_DIR)/libcr100emur.so.$(VERSION)
SHARED_ABI := $(BUILD_DIR)/libcr100emur.so.$(ABI_VERSION)
SHARED_LINK := $(BUILD_DIR)/libcr100emur.so
CLI := $(BUILD_DIR)/cr100-read
DUMP_CLI := $(BUILD_DIR)/cr100-dump
EXAMPLE := $(BUILD_DIR)/read-once
CPP_EXAMPLE := $(BUILD_DIR)/read-once-cpp
EVENT_EXAMPLE := $(BUILD_DIR)/read-events
CPP_EVENT_EXAMPLE := $(BUILD_DIR)/read-events-cpp
TEST := $(BUILD_DIR)/test-parser
READER_TEST := $(BUILD_DIR)/test-reader
CPP_TEST := $(BUILD_DIR)/test-cpp

.PHONY: all clean test examples install uninstall install-udev uninstall-udev \
	python-install python-test python-wheel test-all

all: $(STATIC_LIB) $(SHARED_LINK) $(CLI) $(DUMP_CLI)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(LIB_OBJECT): src/cr100emur.c include/cr100emur.h | $(BUILD_DIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

$(STATIC_LIB): $(LIB_OBJECT)
	$(AR) rcs $@ $<

$(SHARED_REAL): $(LIB_OBJECT)
	$(CC) -shared -Wl,-soname,libcr100emur.so.$(ABI_VERSION) \
		$(LDFLAGS) $< -o $@

$(SHARED_ABI): $(SHARED_REAL)
	ln -sf $(notdir $(SHARED_REAL)) $@

$(SHARED_LINK): $(SHARED_ABI)
	ln -sf $(notdir $(SHARED_ABI)) $@

$(CLI): src/cr100-read.c $(STATIC_LIB) include/cr100emur.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(STATIC_LIB) $(LDFLAGS) -o $@

$(DUMP_CLI): src/cr100-dump.c $(STATIC_LIB) include/cr100emur.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(STATIC_LIB) $(LDFLAGS) -o $@

$(EXAMPLE): examples/read_once.c $(STATIC_LIB) include/cr100emur.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(STATIC_LIB) $(LDFLAGS) -o $@

$(CPP_EXAMPLE): examples/read_once.cpp $(STATIC_LIB) \
		include/cr100emur.hpp include/cr100emur.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $< $(STATIC_LIB) $(LDFLAGS) -o $@

$(EVENT_EXAMPLE): examples/read_events.c $(STATIC_LIB) include/cr100emur.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(STATIC_LIB) $(LDFLAGS) -o $@

$(CPP_EVENT_EXAMPLE): examples/read_events.cpp $(STATIC_LIB) \
		include/cr100emur.hpp include/cr100emur.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $< $(STATIC_LIB) $(LDFLAGS) \
		$(THREAD_FLAGS) -o $@

$(TEST): tests/test_parser.c $(STATIC_LIB) include/cr100emur.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(STATIC_LIB) $(LDFLAGS) -o $@

$(READER_TEST): tests/test_reader.c $(STATIC_LIB) include/cr100emur.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< $(STATIC_LIB) $(LDFLAGS) -o $@

$(CPP_TEST): tests/test_cpp.cpp $(STATIC_LIB) \
		include/cr100emur.hpp include/cr100emur.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $< $(STATIC_LIB) $(LDFLAGS) \
		$(THREAD_FLAGS) -o $@

test: $(TEST) $(READER_TEST) $(CPP_TEST)
	./$(TEST)
	./$(READER_TEST)
	./$(CPP_TEST)

python-install: all
	"$(PYTHON)" -m pip install --editable . --no-build-isolation

python-test: all
	"$(PYTHON)" -m unittest discover -s python/tests -v

python-wheel: all
	"$(PYTHON)" -m pip wheel . --no-deps --no-build-isolation \
		--wheel-dir dist

test-all: test python-test

examples: $(EXAMPLE) $(CPP_EXAMPLE) $(EVENT_EXAMPLE) $(CPP_EVENT_EXAMPLE)

install: all
	$(INSTALL) -d $(DESTDIR)$(INCLUDEDIR) $(DESTDIR)$(LIBDIR) \
		$(DESTDIR)$(BINDIR)
	$(INSTALL) -m 0644 include/cr100emur.h $(DESTDIR)$(INCLUDEDIR)/
	$(INSTALL) -m 0644 include/cr100emur.hpp $(DESTDIR)$(INCLUDEDIR)/
	$(INSTALL) -m 0644 $(STATIC_LIB) $(DESTDIR)$(LIBDIR)/
	$(INSTALL) -m 0755 $(SHARED_REAL) $(DESTDIR)$(LIBDIR)/
	ln -sf $(notdir $(SHARED_REAL)) \
		$(DESTDIR)$(LIBDIR)/$(notdir $(SHARED_ABI))
	ln -sf $(notdir $(SHARED_ABI)) \
		$(DESTDIR)$(LIBDIR)/$(notdir $(SHARED_LINK))
	$(INSTALL) -m 0755 $(CLI) $(DESTDIR)$(BINDIR)/
	$(INSTALL) -m 0755 $(DUMP_CLI) $(DESTDIR)$(BINDIR)/

uninstall:
	rm -f $(DESTDIR)$(INCLUDEDIR)/cr100emur.h
	rm -f $(DESTDIR)$(INCLUDEDIR)/cr100emur.hpp
	rm -f $(DESTDIR)$(LIBDIR)/libcr100emur.a
	rm -f $(DESTDIR)$(LIBDIR)/libcr100emur.so
	rm -f $(DESTDIR)$(LIBDIR)/libcr100emur.so.$(ABI_VERSION)
	rm -f $(DESTDIR)$(LIBDIR)/libcr100emur.so.$(VERSION)
	rm -f $(DESTDIR)$(BINDIR)/cr100-read
	rm -f $(DESTDIR)$(BINDIR)/cr100-dump

install-udev:
	$(INSTALL) -d $(DESTDIR)$(UDEVDIR)
	$(INSTALL) -m 0644 udev/70-cr100emur.rules $(DESTDIR)$(UDEVDIR)/

uninstall-udev:
	rm -f $(DESTDIR)$(UDEVDIR)/70-cr100emur.rules

clean:
	rm -rf $(BUILD_DIR)
