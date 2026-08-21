# Known KiCad Scripting Issues

## The `SwigPyObject` Corruption (Ghost Pointer Crash)

Yes, this crash is a notorious and very obvious issue in KiCad Plugin development! 

### What is happening inside?

1. **C++ vs Python Separation**: KiCad is written in C++, but it exposes a Python API through a wrapper called SWIG. When you open a board, KiCad creates a `BOARD` object in C++ memory, and SWIG gives the Python plugin a "pointer" (reference) to that exact spot in memory.
2. **The "Revert to Saved" Event**: When you click "Revert to Saved", the KiCad C++ core completely destroys that `BOARD` object in memory and deletes it to make room to load the fresh file from your hard drive. It then creates a brand new `BOARD` object at a *different* memory address.
3. **The Ghost Pointer**: Our Kaibridge plugin runs constantly in the background. It does not get notified that the C++ core destroyed the board. Our plugin still holds the pointer to the *old, deleted* memory address.
4. **The Crash (`SwigPyObject`)**: When our script runs `pcbnew.GetBoard()` to talk to KiCad, SWIG realizes the memory it points to is dead. Instead of crashing your entire computer with a "Segmentation Fault", SWIG safely wraps the dead pointer in a generic, empty `SwigPyObject`.
5. **The Error**: Because a `SwigPyObject` is just an empty placeholder, it has no KiCad methods. When our script tries to do `board.GetTracks()`, Python immediately throws `AttributeError: 'SwigPyObject' object has no attribute 'GetTracks'` because the object is dead!

### Why closing just the PCB Editor doesn't fix it

In KiCad, the Python scripting engine is permanently tied to the *main Project Manager process*, not the PCB Editor window. Closing the PCB Editor window only closes the GUI, but the background Python engine (still holding the ghost pointer) stays alive in the main KiCad process.

**The Solution:** You have to kill the entire `kicad.exe` process (which restarts the Python engine from scratch) to force SWIG to grab the correct, new memory address!
