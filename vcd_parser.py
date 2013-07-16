#!python
'''
   Copyright  2013  Gordon McGregor

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.



  A basic self contained VCD parser object

  Walks through the definitions constructing the appropriate signal references.
  Caches XMR paths if and when the signal value changes in the dump for future reference.
  Needs some hooks for callbacks on signal changes and methods to allow sampling of a signal with an appropriate clock reference


  Refer to IEEE SystemVerilog standard 1800-2009 for VCD details Section 21.7 Value Change Dump (VCD) files

  Based on toggle count sample code from Donald 'Paddy' McCarthy
  http://paddy3118.blogspot.com/2008/03/writing-vcd-to-toggle-count-generator.html

'''

from itertools import dropwhile, takewhile, izip
from collections import defaultdict
import sys

from vcd_watcher import VcdWatcher, VcdTracker

class VCD(object):
  ''' A parser object for VCD files.  Reads definitions and walks through the value changes'''
     
  def __init__(self):

    keyword_functions = {
    # declaration_keyword ::=
    "$comment":        self.drop_declaration,
    "$date":           self.save_declaration,
    "$enddefinitions": self.vcd_enddefinitions,
    "$scope":          self.vcd_scope,
    "$timescale":      self.save_declaration,
    "$upscope":        self.vcd_upscope,
    "$var":            self.vcd_var,
    "$version":        self.save_declaration,
    # simulation_keyword ::=
    "$dumpall":        self.vcd_dumpall,
    "$dumpoff":        self.vcd_dumpoff,
    "$dumpon":         self.vcd_dumpon,
    "$dumpvars":       self.vcd_dumpvars,
    "$end":            self.vcd_end,
    }

    self.keyword_dispatch = defaultdict(self.parse_error, keyword_functions)
 
    self.scope = []
    self.now = 0
    self.idcode2references = defaultdict(list)
    self.xmr_cache = dict()
    self.end_of_definitions = False
    self.changes = {}
    self.watchers = []
    self.debug = True

  def get_id(self, xmr):
    search_path = xmr.split('.')

    for id in self.idcode2references:
      (var_type, size, reference) = self.idcode2references[id][0]
      match = True  
      for depth, node in enumerate(search_path):
        var_type, name = reference[depth]
        if node == name:
          continue
        else:
          match = False
          break
      if match:
        return id

    raise ValueError('No match for ', xmr)


  def show_nets(self):
    for id in self.idcode2references:
      print self.get_xmr(id)


  def get_xmr(self, id):
    if id in self.xmr_cache:
      return self.xmr_cache[id]

    (type, size, refs) = self.idcode2references[id][0]
    xmr = ".".join([ v for (k, v) in refs])
    self.xmr_cache[id] = xmr
    return xmr


  def scaler_value_change(self, value, id):
    self.changes[id] = value


  def vector_value_change(self, format, number, id):
    self.changes[id] = (format, number)


  def register_watcher(self, watcher):
    self.watchers.append(watcher)


  def deregister_watcher(self, watcher):
    self.watchers.remove(watcher)


  def update_time(self, next_time):
    current_time = self.now

    if self.debug: 
      print "Current time is ", self.now, 'changing to ', next_time
      for change in self.changes:
        print self.get_xmr(change), self.changes[change]

    for watcher in self.watchers:
      update_needed = False
      for signal in watcher._sensitive_ids:
        if signal in self.changes:
          update_needed = True

      if update_needed:
        collected_changes = {}
        for signal in watcher._watching_ids:
          if signal in self.changes:
            collected_changes[signal] = self.changes[signal]

        watcher.update(collected_changes, vcd)

    self.changes = {}
    self.now = next_time


  def parse(self, fh):
    # open the VCD file and create a token generator
    tokeniser = (word for line in fh for word in line.split() if word)

    for count, token in enumerate(tokeniser):
      # parse VCD until the end of definitions
      if not vcd.end_of_definitions:
        self.keyword_dispatch[token](tokeniser, token)
      else:
        # Working through changes
        c, rest = token[0], token[1:]
        if c == '$':
          # skip $dump* tokens and $end tokens in sim section
          continue
        elif c == '#':
          self.update_time(rest)
        elif c in '01xXzZ':
          self.scaler_value_change(value=c, id=rest)
        elif c in 'bBrR':
          self.vector_value_change(format=c.lower(), number=rest, id=tokeniser.next())
        else:
          raise "Don't understand: %s After %i words" % (token, count)


  def parse_error(self, tokeniser, keyword):
    raise "Don't understand keyword: " + keyword


  def drop_declaration(self, tokeniser, keyword):
    dropwhile(lambda x: x != "$end", tokeniser).next()


  def save_declaration(self, tokeniser, keyword):
    vcd.__setattr__(keyword.lstrip('$'),
                    " ".join( takewhile(lambda x: x != "$end", tokeniser)) )


  def vcd_enddefinitions(self, tokeniser, keyword):
    self.end_of_definitions = True
    self.drop_declaration(tokeniser, keyword)
    
    for watcher in self.watchers:
      watcher.update_ids(self)
    

  def vcd_scope(self, tokeniser, keyword):
    self.scope.append( tuple(takewhile(lambda x: x != "$end", tokeniser)))
    
    
  def vcd_upscope(self, tokeniser, keyword):
    self.scope.pop()
    tokeniser.next()
    
    
  def vcd_var(self, tokeniser, keyword):
    data = tuple(takewhile(lambda x: x != "$end", tokeniser))
    (var_type, size, identifier_code, reference) = data[:4] # ignore range on identifier ( TODO  Fix this )
    reference = vcd.scope + [('var', reference)]
    self.idcode2references[identifier_code].append( (var_type, size, reference))
    
    
  def vcd_dumpall(self, tokeniser, keyword): 
    pass


  def vcd_dumpoff(self, tokeniser, keyword): 
    pass


  def vcd_dumpon(self, tokeniser, keyword): 
    pass


  def vcd_dumpvars(self, tokeniser, keyword): 
    pass


  def vcd_end(self, tokeniser, keyword):
    if not self.end_of_definitions:
      parse_error(tokeniser, keyword)



if __name__ == '__main__':

  vcd = VCD()

  watcher = VcdWatcher()
  watcher.set_hierarchy('top.m1')
  watcher.add_sensitive('net3')
  watcher.add_watching('net2')

  watcher.set_tracker(VcdTracker)

  vcd.register_watcher(watcher)

  with open(sys.argv[1]) as vcd_file:
    try:
      vcd.parse(vcd_file)
    except ValueError as e:
      print e
      vcd.show_nets()
