import pyvisa, PySimpleGUI as sg, matplotlib.pyplot as plt, os
from time import sleep
from datetime import datetime

rm = pyvisa.ResourceManager()
print(rm.list_resources())
try:
    amplifier_port = "ASRL8::INSTR"
    oscil_port = "USB0::0x1AB1::0x04CE::DS1ZA161450725::INSTR"
    amplifier = rm.open_resource(amplifier_port)
    oscil = rm.open_resource(oscil_port)
except Exception:
    print("Default amplifier/oscillator ports not found. If program is working as intended ignore this error.")
    amplifier_port, oscil_port = "", ""
    amplifier, oscil = 0,0

#SLVL 0.77 = 80Vacpp
#SLVL 1.05 = 100Vacpp
#amplifier.write("SLVL 1.05")

#VTS1 = 80acpp, 100dc
#VTS2 = 100acpp, 120dc

vel_range = 5
disp_range = 8
LDV_mode = "vel"
save_ac = True

sg.set_options(font=("Courier",15))
sg.theme('NeutralBlue')
FrequencyController = [
    [sg.Text("Start Frequency ", size=(15,1)), sg.InputText(default_text="400", key="StartFreq", size=(10,1))],
    [sg.Text("End Frequency", size=(15,1)), sg.InputText(default_text="1000", key="EndFreq", size=(10,1))],
    [sg.Text("Delta", size=(15,1)), sg.InputText(default_text="25", key="DeltaFreq", size=(10,1))],
    [sg.Text("Delay (s)", size=(15,1)), sg.InputText(default_text="1", key="TimePerFreq", size=(10,1))],
    [sg.Text("Vel Range", size=(15,1)), sg.InputText(default_text="25", key="VelRange", size=(10,1))],
    [sg.Button("Range"), sg.Button("Init"), sg.Button("Next")]
]
FileBrowser = [
    [sg.Text("File Path", size=(15,1)), sg.Input(size=(10,1), key="Path"), sg.FolderBrowse("Browse", size=(10,1))],
    [sg.Text("File Name", size=(15,1)), sg.Input(default_text="$m30C", key="Filename", size=(10,1)), sg.Button("Open", size=(10,1))]
]
AmplifierSelector = [
    [sg.Text("Amplifier Port:")],
    [sg.Combo([port for port in rm.list_resources()], default_value=amplifier_port, key="amplifier_port_selected", enable_events=True, size=(15,1))]
]
OscilSelector = [
    [sg.Text("Oscilloscope Port:")],
    [sg.Combo([port for port in rm.list_resources()], default_value=oscil_port, key="oscil_port_selected", enable_events=True, size=(15,1))]
]
Options = [
    [sg.Radio("Vel", "LDV", default=True, key="LDV_mode_vel", enable_events=True), sg.Radio("Disp", "LDV", key="LDV_mode_disp", enable_events=True), sg.Text("|"), sg.Checkbox("Save AC?", default=True, key="saveAC")]
]
Channels = [
    [sg.Text("Oscillator Channels:")],
    [sg.Text("Amp"),sg.Input(default_text=1,size=(4,1), key="ampChannel"), sg.Text("AC1"),sg.Input(default_text=2,size=(4,1), key="ac1Channel"), sg.Text("AC2"),sg.Input(default_text=3,size=(4,1), key="ac2Channel")]
]


layout = [FrequencyController[:], [sg.Text("-"*40)], FileBrowser[:], [sg.Text("-"*40)], AmplifierSelector[:], OscilSelector[:], Options[:], [sg.Text("-"*40)], Channels[:]]
window = sg.Window('Resonance Measurer', layout, finalize=True, resizable=True, grab_anywhere=True)

def vamp2disp(vel, freq):
    global vel_range
    return vel*1000*vel_range / (4*3.14*freq)

def damp2disp(disp):
    return disp/2*disp_range

def collect_data(values):
    global vel_range
    vel_range = int(values["VelRange"])
    freq_list = []
    amp_list = []
    disp_list = []
    ac1_list = []
    ac2_list = []
    try:
        sf = int(values["StartFreq"])
        ef = int(values["EndFreq"])
        df = int(values["DeltaFreq"])
        t = float(values["TimePerFreq"])
    except:
        sg.Popup("Error", "Invalid Data Types: Need to be {Int, Int, Int, Float}")
        return
    for freq in range(sf, ef+1, df):
        amplifier.write("FREQ %d" % freq)
        freq_list.append(freq)
        oscil.write(':SINGle')
        amp_list.append(oscil.query_ascii_values(':MEASure:ITEM? Vpp,CHANnel'+values["ampChannel"])[0])
        if values["saveAC"]:
            ac1_list.append(oscil.query_ascii_values(':MEASure:ITEM? Vpp,CHANnel'+values["ac1Channel"])[0])
            ac2_list.append(oscil.query_ascii_values(':MEASure:ITEM? Vpp,CHANnel'+values["ac2Channel"])[0])
        disp = vamp2disp(amp_list[-1],freq) if LDV_mode=="vel" else damp2disp(amp_list[-1])
        disp_list.append(disp)
        sleep(t)
    plot = plt.plot(freq_list, disp_list, ".k")
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Displacement (um)")

    indexes = [i for i in range(1,len(disp_list)-1) if disp_list[i]-((disp_list[i-1]+disp_list[i+1])/2) < 3]
    disp_list = [disp_list[i] for i in indexes]
    freq_list = [freq_list[i] for i in indexes]
    amp_list = [amp_list[i] for i in indexes]
    Imax = max(disp_list)
    fr = freq_list[disp_list.index(Imax)]
    near_threshf = [freq_list[i] for i in range(len(disp_list)) if abs(disp_list[i]-((Imax-disp_list[0])/2+disp_list[0]))<1.5]
    try:
        bandwidth = max(near_threshf) - min(near_threshf)
        qfactor = fr / bandwidth if bandwidth > 50 else "Not Enough Data"
    except:
        bandwidth = 0
        qfactor = "Couldnt find FWHM points"


    filename =  values["Path"] + "/" + values["Filename"] + ".txt"
    filename = filename.replace("$m", LDV_mode)
    filename = filename.replace("$t", str(datetime.now().strftime("%H.%M")))
    file = open(filename, "w")
    file.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S") + "\n")
    file.write("Temp [C] =	\n")
    file.write("fr [Hz] =	" + str(fr) + "\n")
    file.write("Q = " + str(qfactor) + "\n")
    file.write("f[Hz]	A[V]	A [µm]\n")
    for i in range(len(freq_list)):
        file.write(str(freq_list[i]) + "	" + str(amp_list[i]) + "	" + str(disp_list[i]) + "\n")
    if values["saveAC"]:
        file.write("\n\nAC:\nAC[V]	AC[V]\n")
        for i in range(len(ac1_list)):
            file.write(str(ac1_list[i]) + "	" + str(ac2_list[i]) + "\n")



while True:
    event, values = window.read(timeout=200)
    if event == sg.WIN_CLOSED:
        break
    elif event == "Range":
        collect_data(values)
    elif event == "Next":
        current_freq = amplifier.query_ascii_values("FREQ?")[0]
        amplifier.write("FREQ %d" % (current_freq + int(values["DeltaFreq"])))
    elif event == "Init":
        amplifier.write("FREQ %d" % int(values["StartFreq"]))
    elif event == "amplifier_port_selected":
        amplifier = rm.open_resource(values["amplifier_port_selected"])
        sg.Popup("*IDN?", str(amplifier.query("*IDN?")))
    elif event == "oscil_port_selected":
        oscil = rm.open_resource(values["oscil_port_selected"])
        sg.Popup("*IDN?", str(oscil.query("*IDN?")))
    elif event in ["LDV_mode_vel", "LDV_mode_disp"]:
        LDV_mode = event.split("_")[-1]
    elif event == "Open":
        path = values["Path"]
        path = os.path.realpath(path)
        os.startfile(path)
    elif event == "Graph":
        plt.show()

try:
    oscil.close()
    amplifier.close()
except:
    print("Invalid oscillator/amplifier ports.")
window.close()
