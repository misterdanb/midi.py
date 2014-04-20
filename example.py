from midi import *

if __name__ == '__main__':
    midi_file = MidiFile('/path/to/midi_file.mid')

    print(midi_file)

    for chunk in midi_file:
        print(chunk)

        if chunk.chunk_type == ChunkType.m_trk:
            for mtrk_event in chunk:
                print(mtrk_event)
                print(mtrk_event.event)
