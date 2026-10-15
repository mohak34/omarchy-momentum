# omarchy-momentum

Sennheiser Momentum 4 headphones in the Omarchy bar. Battery, codec, noise cancelling, transparency, anti-wind and the headphone settings, straight over Bluetooth. No Sennheiser app, no account.

- Click: open the headphone panel
- Right-click: cycle noise mode (Adaptive, Custom, Off)
- Scroll: transparency, in Custom mode

In the panel:

- **Header:** battery, and the codec and sample rate of the current audio output. Over the USB cable it shows the cable's format instead.
- **Noise:** Adaptive lets the headphones pick the noise cancelling level. Custom uses the transparency slider. Off turns noise cancelling off.
- **Transparency:** how much outside sound comes through in Custom mode, from Blocked (full noise cancelling) to Let in.
- **Anti-wind:** Off, Auto or Max.
- **Sound, Behaviour, Auto power off:** the same switches as the Sennheiser app. Settings your firmware does not have are hidden.

## Requirements

- Omarchy 4 (Quattro shell)
- The headphones paired and connected over Bluetooth. Over the USB cable alone only the audio output is shown.

## Install

```sh
omarchy plugin add https://github.com/mohak34/omarchy-momentum.git --yes
omarchy plugin enable mohak34.momentum
```

Nothing to build. The widget runs `m4.py`, a standard-library Python script that reads or changes the headphones once and exits, so nothing stays running between clicks. While the panel is closed it refreshes every two minutes (configurable in the widget settings), and only talks to the headphones while they are connected over Bluetooth.

From a terminal:

```sh
python3 ~/.config/omarchy/plugins/mohak34.momentum/m4.py status
python3 ~/.config/omarchy/plugins/mohak34.momentum/m4.py set noise adaptive
```

## Not supported

- **EQ, firmware updates, voice prompts:** not implemented.
- **Hi-res audio mode:** needs aptX Adaptive, which Linux does not have.
- **Charging state:** the headphones only announce it, they never answer when asked, and the script does not stay connected to listen.

## Credits

Command ids come from the reverse engineering in [DanSmith888/omarchy-momentum4](https://github.com/DanSmith888/omarchy-momentum4) and [timmo001/omarchy-momentumctl](https://github.com/timmo001/omarchy-momentumctl).

## Remove

```sh
omarchy plugin remove mohak34.momentum
```
