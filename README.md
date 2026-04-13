# Syrup
Have you ever tried to share one of your **awesome** rices but found it incredibly hard?
Don't worry. Syrup has you covered.
Syrup is a folder sharing tool, mostly used as a rice sharing tool.
Here's how it works:
- You get a folder, and put your files in it (this can even be ~/.config!)
- Run `syrup package` and fill out the 'form'.
- Syrup makes you a .syp file.
- Share the .syp file.
- The other party(s) can then run `syrup install <filename>`.
- Syrup will then 'pour' (install) that .syp file.
You might be wondering, how does this differ from just giving the other party a .zip?
Well, Syrup extracts the .syp to the **exact** directory it was packaged from.
Let's say: You make a .syp of `/home/alice/.config`, and your friend installs that .syp, it won't make a folder called `/home/alice/.config` and extract there, it'll install to `/home/bob/.config`. (Where `alice` is your username and `bob` is your friend's.) Keep in mind, at the moment, it WILL erase **everything** in the destination folder.
Interested?
You can join our Discord server here: https://discord.gg/NNFWarxrXA,
GitHub: https://github.com/NytrixLabs/Syrup
