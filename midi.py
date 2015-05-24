import sys
import os
import struct
import array

from enum import Enum

def bytes_to_uint16(byte_list):
    return struct.unpack('>H', byte_list[:4])[0]

def uint16_to_bytes(value):
    return struct.pack('>H', value)

def bytes_to_uint24(byte_list):
    return struct.unpack('>I', b'\x00' + byte_list[:3])[0]

def uint24_to_bytes(value):
    return struct.pack('>I', value)[1:4]

def bytes_to_uint32(byte_list):
    return struct.unpack('>I', byte_list[:4])[0]

def uint32_to_bytes(value):
    return struct.pack('>I', value)

def bytes_to_str(byte_list):
    return byte_list.decode('utf-8')

def str_to_bytes(value):
    return value.encode('utf-8')

def enum_values(enum):
    return list(map(lambda x: x.value, enum))

def enum_names(enum):
    return list(map(lambda x: x.name, enum))

def decode_variable_length_value(byte_list):
    value = 0

    tmp_pos = 0

    while byte_list[tmp_pos] & 0b10000000 != 0:
        value_part = byte_list[tmp_pos] & 0b01111111
        value |= value_part
        value <<= 7

        tmp_pos += 1

    value_part = byte_list[tmp_pos] & 0b01111111
    value |= value_part

    tmp_pos += 1

    return(value, tmp_pos)

def encode_variable_length_value(value):
    bytes_repr = bytearray()

    bytes_repr.insert(0, value & 0b01111111)
    value >>= 7

    while value & 0b01111111 != 0:
        bytes_repr.insert(0, (value & 0b01111111) | 0b10000000)
        value >>= 7

    return(bytes(bytes_repr))

class MidiException(Exception):
    pass

class MidiFile():
    def __init__(self, path):
        self.path = path
        self.chunks = []

        try:
            with open(path, 'rb') as midi_file:
                midi_data = midi_file.read()

                file_pos = 0

                while file_pos < len(midi_data):
                    new_chunk = Chunk(midi_data[file_pos:])
                    self.chunks.append(new_chunk)

                    file_pos += 8 + new_chunk.length
        except:
            raise(MidiException('Could not open midi file'))

    def __iter__(self):
        for chunk in self.chunks:
            yield(chunk)

    def __repr__(self):
        return('<File: ' + self.path + '>')

    def export(self, path='out.mid'):
        with open(path, 'wb') as midi_file:
            for chunk in self.chunks:
                midi_file.write(chunk.to_bytes())


class ChunkType(Enum):
    m_thd = 'MThd'
    m_trk = 'MTrk'

class Chunk():
    def __init__(self, byte_list):
        self.chunk_type = ChunkType(bytes_to_str(byte_list[:4]))
        self.length = bytes_to_uint32(byte_list[4:8])

        if self.chunk_type == ChunkType.m_thd:
            if self.length == 6:
                self.file_format = bytes_to_uint16(byte_list[8:10])
                self.tracks_count = bytes_to_uint16(byte_list[10:12])
                self.division = bytes_to_uint16(byte_list[12:14])
            else:
                raise(MidiException('Invalid MThd chunk'))
        elif self.chunk_type == ChunkType.m_trk:
            self.mtrk_events = []

            tmp_pos = 8

            while tmp_pos < 8 + self.length:
                new_mtrk_event = MTrkEvent(byte_list[tmp_pos:])

                self.mtrk_events.append(new_mtrk_event)
                tmp_pos += new_mtrk_event.length

    def __iter__(self):
        if self.chunk_type == ChunkType.m_thd:
            yield(None)
        else:
            for mtrk_event in self.mtrk_events:
                yield(mtrk_event)

    def __repr__(self):
        if self.chunk_type == ChunkType.m_thd:
            return('<Chunk Type: ' + self.chunk_type.name + ', ' +
                   'Length: ' + str(self.length) + ', ' +
                   'File format: ' + str(self.file_format) + ', ' + 
                   'Tracks count: ' + str(self.tracks_count) + ', ' + 
                   'Division: ' + str(self.division) + '>')
        elif self.chunk_type == ChunkType.m_trk:
            return('<Chunk Type: ' + self.chunk_type.name + '. ' +
                   'Length: ' + str(self.length) + '>')

    def to_bytes(self):
        bytes_repr = bytearray()

        bytes_repr += str_to_bytes(self.chunk_type.value);
        bytes_repr += uint32_to_bytes(self.length);

        if self.chunk_type == ChunkType.m_thd:
            bytes_repr += uint16_to_bytes(self.file_format)
            bytes_repr += uint16_to_bytes(self.tracks_count)
            bytes_repr += uint16_to_bytes(self.division)
        elif self.chunk_type == ChunkType.m_trk:
            for mtrk_event in self.mtrk_events:
                bytes_repr += mtrk_event.to_bytes()

        return(bytes(bytes_repr))

class MTrkEvent():
    def __init__(self, byte_list):
        self.delta_time, self.length = decode_variable_length_value(byte_list)

        tmp_pos = self.length

        event_code = byte_list[tmp_pos]

        if (event_code & 0b11110000) in enum_values(MidiEventType):
            self.event = MidiEvent(byte_list[tmp_pos:])
        elif event_code in enum_values(SystemEventType):
            self.event = SystemEvent(byte_list[tmp_pos:])
        elif event_code == 0b11111111:
            self.event = MetaEvent(byte_list[tmp_pos:])
        else:
            raise(MidiException('No such event'))

        self.length += self.event.length

    def __repr__(self):
        return('<Delta time: ' + str(self.delta_time) + ', ' +
               'Event: ' + self.event.__class__.__name__ + '>')

    def to_bytes(self):
        bytes_repr = bytearray()

        bytes_repr += encode_variable_length_value(self.delta_time)
        bytes_repr += self.event.to_bytes()

        return(bytes(bytes_repr))

class MidiEventType(Enum):
    note_off = 0b10000000
    note_on = 0b10010000
    note_pressure = 0b10100000
    control_change = 0b10110000
    program_change = 0b11000000
    channel_pressure = 0b11010000
    pitch_change = 0b11100000

class MidiEvent():
    def __init__(self, byte_list):
        try:
            self.event_type = MidiEventType(byte_list[0] & 0b11110000)
            self.channel_number = byte_list[0] & 0b00001111

            if self.event_type == MidiEventType.note_off or \
               self.event_type == MidiEventType.note_on:
                self.note = byte_list[1]
                self.velocity = byte_list[2]

                self.length = 3
            elif self.event_type == MidiEventType.note_pressure:
                self.note = byte_list[1]
                self.pressure = byte_list[2]

                self.length = 3
            elif self.event_type == MidiEventType.control_change:
                self.control_number = byte_list[1]
                self.new_value = byte_list[2]

                self.length = 3
            elif self.event_type == MidiEventType.program_change:
                self.program_number = byte_list[1]

                self.length = 2
            elif self.event_type == MidiEventType.channel_pressure:
                self.channel_pressure = byte_list[1]

                self.length = 2
            elif self.event_type == MidiEventType.pitch_change:
                self.bottom = byte_list[1]
                self.next_value = byte_list[2]

                self.length = 3
        except ValueError:
            raise(MidiException('No such midi event type'))

    def __repr__(self):
        if self.event_type == MidiEventType.note_off or \
           self.event_type == MidiEventType.note_on:
            return('<Midi event type: ' + self.event_type.name + ', ' +
                   'Channel number: ' + str(self.channel_number) + ', ' +
                   'Note number: ' + str(self.note) + ', ' +
                   'Velocity: ' + str(self.velocity) + '>')
        elif self.event_type == MidiEventType.note_pressure:
            return('<Midi event type: ' + self.event_type.name + ', ' +
                   'Channel number: ' + str(self.channel_number) + ', ' +
                   'Note number: ' + str(self.note) + ', ' +
                   'Pressure: ' + str(self.pressure) + '>')
        elif self.event_type == MidiEventType.control_change:
            return('<Midi event type: ' + self.event_type.name + '. ' +
                   'Channel number: ' + str(self.channel_number) + ', ' +
                   'Controller number: ' + str(self.control_number) + ', ' +
                   'New Value: ' + str(self.new_value) + '>')
        elif self.event_type == MidiEventType.program_change:
            return('<Midi event type: ' + self.event_type.name + ', ' +
                   'Channel number: ' + str(self.channel_number) + ', ' +
                   'New program number: ' + str(self.program_number) + '>')
        elif self.event_type == MidiEventType.channel_pressure:
            return('<Midi event type: ' + self.event_type.name + ', ' +
                   'Channel number: ' + str(self.channel_number) + ', ' +
                   'Pressure: ' + str(self.channel_pressure) + '>')
        elif self.event_type == MidiEventType.pitch_change:
            return('<Midi event type: ' + self.event_type.name + ', ' +
                   'Channel: ' + str(self.channel_number) + ', ' +
                   'Bottom: ' + str(self.bottom) + ', ' +
                   'Next Value: ' + str(self.next_value) + '>')

    def to_bytes(self):
        bytes_repr = bytearray()

        bytes_repr.append(self.event_type.value | self.channel_number)

        if self.event_type == MidiEventType.note_off or \
           self.event_type == MidiEventType.note_on:
            bytes_repr.append(self.note)
            bytes_repr.append(self.velocity)
        elif self.event_type == MidiEventType.note_pressure:
            bytes_repr.append(self.note)
            bytes_repr.append(self.pressure)
        elif self.event_type == MidiEventType.control_change:
            bytes_repr.append(self.control_number)
            bytes_repr.append(self.new_value)
        elif self.event_type == MidiEventType.program_change:
            bytes_repr.append(self.program_number)
        elif self.event_type == MidiEventType.channel_pressure:
            bytes_repr.append(self.channel_pressure)
        elif self.event_type == MidiEventType.pitch_change:
            bytes_repr.append(self.bottom)
            bytes_repr.append(self.next_value)

        return(bytes(bytes_repr))

class SystemEventType(Enum):
    exclusive = 0b11110000
    common_song_position = 0b11110010
    common_song_select = 0b11110011
    common_tune_request = 0b11110110
    common = 0b11110111
    real_time_timing_clock = 0b11111000
    real_time_start = 0b11111010
    real_time_continue = 0b11111011
    real_time_stop = 0b11111100
    real_time_active_sensing = 0b11111110

class SystemEvent():
    def __init__(self, byte_list):
        try:
            self.event_type = SystemEventType(byte_list[0])

            if self.event_type == SystemEventType.exclusive or \
               self.event_type == SystemEventType.common:
                self.length = 2

                tmp_pos = 1

                while byte_list[tmp_pos] != SystemEventType.common.value:
                    tmp_pos += 1
                    self.length += 1

                self.payload = byte_list[1:self.length - 1]
            elif self.event_type == SystemEventType.common_song_position:
                self.length = 3
            elif self.event_type == SystemEventType.common_song_select:
                self.length = 2
            elif self.event_type == SystemEventType.common_tune_request:
                self.length = 1
            elif self.event_type == SystemEventType.real_time_timing_clock:
                self.length = 1
            elif self.event_type == SystemEventType.real_time_start:
                self.length = 1
            elif self.event_type == SystemEventType.real_time_continue:
                self.length = 1
            elif self.event_type == SystemEventType.real_time_stop:
                self.length = 1
            elif self.event_type == SystemEventType.real_time_active_sensing:
                self.length = 1
            elif self.event_type == SystemEventType.real_time_reset:
                self.length = 1

        except ValueError:
            raise(MidiException('No such system event type'))

    def __repr__(self):
        if self.event_type == SystemEventType.exclusive or \
           self.event_type == SystemEventType.common:
            return('<System event type: ' + self.event_type.name + ', ' +
                   'Payload: ' + str(self.payload) + '>')
        else:
            return('<System event type: ' + self.event_type.name + '>')

    def to_bytes(self):
        bytes_repr = bytearray()

        bytes_repr.append(self.event_type.value)

        if self.event_type == SystemEventType.exclusive or \
           self.event_type == SystemEventType.common:
            bytes_repr += self.payload
            bytes_repr.append(SystemEventType.common.value)
        elif self.event_type == SystemEventType.common_song_position:
            # todo
            bytes_repr.append(0)
            bytes_repr.append(0)
        elif self.event_type == SystemEventType.common_song_select:
            # todo
            bytes_repr.append(0)
        elif self.event_type == SystemEventType.common_tune_request:
            pass
        elif self.event_type == SystemEventType.real_time_timing_clock:
            pass
        elif self.event_type == SystemEventType.real_time_start:
            pass
        elif self.event_type == SystemEventType.real_time_continue:
            pass
        elif self.event_type == SystemEventType.real_time_stop:
            pass
        elif self.event_type == SystemEventType.real_time_active_sensing:
            pass
        elif self.event_type == SystemEventType.real_time_reset:
            pass

        return(bytes(bytes_repr))

class MetaEventType(Enum):
    sequence_number = 0b00000000
    text = 0b00000001
    copyright_notice = 0b00000010
    text_sequence_or_track_name = 0b00000011
    instrument_name = 0b00000100
    lyric = 0b00000101
    marker = 0b0000110
    cue_point = 0b00000111
    channel_prefix = 0b00100000
    end_of_track = 0b00101111
    tempo = 0b01010001
    smpte_offset = 0b01010100
    time_signature = 0b01011000
    key_signature = 0b01011001
    sequencer_specific_payload = 0b01111111

class MetaEvent():
    def __init__(self, byte_list):
        if byte_list[0] == 0b11111111:
            try:
                self.event_type = MetaEventType(byte_list[1])
                self.payload_length, self.length = decode_variable_length_value(byte_list[2:])

                tmp_pos = 2 + self.length

                payload = byte_list[tmp_pos:tmp_pos + self.payload_length]

                if self.event_type == MetaEventType.sequence_number:
                    self.sequence_number = bytes_to_uint16(payload)
                elif self.event_type == MetaEventType.text:
                    self.text = bytes_to_str(payload)
                elif self.event_type == MetaEventType.copyright_notice:
                    self.copyright_notice = bytes_to_str(payload)
                elif self.event_type == MetaEventType.text_sequence_or_track_name:
                    self.text_sequence_or_track_name = bytes_to_str(payload)
                elif self.event_type == MetaEventType.instrument_name:
                    self.instrument_name = bytes_to_str(payload)
                elif self.event_type == MetaEventType.lyric:
                    self.lyric = bytes_to_str(payload)
                elif self.event_type == MetaEventType.marker:
                    self.marker = bytes_to_str(payload)
                elif self.event_type == MetaEventType.cue_point:
                    self.cue_point = bytes_to_str(payload)
                elif self.event_type == MetaEventType.channel_prefix:
                    self.channel_prefix = payload[0]
                elif self.event_type == MetaEventType.end_of_track:
                    pass
                elif self.event_type == MetaEventType.tempo:
                    self.tempo = bytes_to_uint24(payload)
                elif self.event_type == MetaEventType.smpte_offset:
                    self.smpte_offset = payload
                elif self.event_type == MetaEventType.time_signature:
                    self.time_signature = payload
                elif self.event_type == MetaEventType.key_signature:
                    self.key_signature = payload
                elif self.event_type == MetaEventType.sequencer_specific_payload:
                    self.sequencer_specific_payload = payload

                self.length += 2 + self.payload_length
            except:
                raise(MidiException('No such meta event'))
        else:
            raise(MidiException('Not a meta event'))

    def __repr__(self):
        if self.event_type == MetaEventType.sequence_number:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Sequence number: ' + str(self.sequence_number) + '>')
        elif self.event_type == MetaEventType.text:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Text: ' + self.text + '>')
        elif self.event_type == MetaEventType.copyright_notice:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Copyright notice: ' + self.copyright_notice + '>')
        elif self.event_type == MetaEventType.text_sequence_or_track_name:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Text sequence or track name: ' + self.text_sequence_or_track_name + '>')
        elif self.event_type == MetaEventType.instrument_name:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Instrument name: ' + self.instrument_name + '>')
        elif self.event_type == MetaEventType.lyric:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Lyric: ' + self.lyric + '>')
        elif self.event_type == MetaEventType.marker:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Marker: ' + self.marker + '>')
        elif self.event_type == MetaEventType.cue_point:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Cue point: ' + self.cue_point + '>')
        elif self.event_type == MetaEventType.channel_prefix:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Channel prefix: ' + str(self.channel_prefix) + '>')
        elif self.event_type == MetaEventType.end_of_track:
            return('<Meta event type: ' + self.event_type.name + '>')
        elif self.event_type == MetaEventType.tempo:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Tempo: ' + str(self.tempo) + '>')
        elif self.event_type == MetaEventType.smpte_offset:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'SMPTE offset: ' + str(self.smpte_offset) + '>')
        elif self.event_type == MetaEventType.time_signature:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Time signature: ' + str(self.time_signature) + '>')
        elif self.event_type == MetaEventType.key_signature:
            return('<Meta event type: ' + self.event_type.name + ', ' + 
                   'Key signature: ' + str(self.key_signature) + '>')
        elif self.event_type == MetaEventType.sequencer_specific_payload:
            return('<Meta event type: ' + self.event_type.name + ', ' +
                   'Sequencer specific payload: ' + str(self.sequencer_specific_payload) + '>')

    def to_bytes(self):
        bytes_repr = bytearray()

        bytes_repr.append(0b11111111)
        bytes_repr.append(self.event_type.value)
        bytes_repr += encode_variable_length_value(self.payload_length)

        if self.event_type == MetaEventType.sequence_number:
            bytes_repr += uint16_to_bytes(self.sequence_number)
        elif self.event_type == MetaEventType.text:
            bytes_repr += str_to_bytes(self.text)
        elif self.event_type == MetaEventType.copyright_notice:
            bytes_repr += str_to_bytes(self.copyright_noticed)
        elif self.event_type == MetaEventType.text_sequence_or_track_name:
            bytes_repr += str_to_bytes(self.text_sequence_or_track_name)
        elif self.event_type == MetaEventType.instrument_name:
            bytes_repr += str_to_bytes(self.instrument_name)
        elif self.event_type == MetaEventType.lyric:
            bytes_repr += str_to_bytes(self.lyric)
        elif self.event_type == MetaEventType.marker:
            bytes_repr += str_to_bytes(self.marker)
        elif self.event_type == MetaEventType.cue_point:
            bytes_repr += str_to_bytes(self.cue_point)
        elif self.event_type == MetaEventType.channel_prefix:
            # this is not looking too safe
            bytes_repr.append(self.channel_prefix)
        elif self.event_type == MetaEventType.end_of_track:
            pass
        elif self.event_type == MetaEventType.tempo:
            bytes_repr += uint24_to_bytes(self.tempo)
        elif self.event_type == MetaEventType.smpte_offset:
            bytes_repr += self.smpte_offset
        elif self.event_type == MetaEventType.time_signature:
            bytes_repr += self.time_signature
        elif self.event_type == MetaEventType.key_signature:
            bytes_repr += self.key_signature
        elif self.event_type == MetaEventType.sequencer_specific_payload:
            bytes_repr += self.sequencer_specific_payload

        return(bytes(bytes_repr))

