(function () {
  var noteText = "No audio input. Speech recognition is not implemented.";
  var note = document.getElementById("waveform-note");
  if (note) {
    note.textContent = noteText;
  }
  var bars = document.querySelectorAll("#waveform i");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  var button = document.getElementById("use-microphone");
  if (!button) {
    return;
  }

  function keepStill() {
    if (note) {
      note.textContent = noteText;
    }
  }

  button.addEventListener("click", function () {
    var media = navigator.mediaDevices;
    var Audio = window.AudioContext || window.webkitAudioContext;
    if (!media || typeof media.getUserMedia !== "function" || !Audio) {
      keepStill();
      return;
    }
    media.getUserMedia({ audio: true }).then(function (stream) {
      if (reduced.matches) {
        stream.getTracks().forEach(function (track) {
          track.stop();
        });
        keepStill();
        return;
      }
      var audio = new Audio();
      var source = audio.createMediaStreamSource(stream);
      var analyser = audio.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);
      var data = new Uint8Array(analyser.frequencyBinCount);

      function paint() {
        if (reduced.matches) {
          return;
        }
        analyser.getByteFrequencyData(data);
        for (var index = 0; index < bars.length; index += 1) {
          var sample = data[index % data.length] / 255;
          bars[index].style.height = (12 + Math.round(sample * 58)) + "%";
        }
        window.requestAnimationFrame(paint);
      }

      paint();
    }).catch(function () {
      keepStill();
    });
  });
}());
