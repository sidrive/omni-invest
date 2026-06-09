importScripts("https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "AIzaSyA0mabuoirwuoOEfIQcbPzcztte0LGJxYQ",
  authDomain: "omni-invest-sentinel-19f55.firebaseapp.com",
  projectId: "omni-invest-sentinel-19f55",
  storageBucket: "omni-invest-sentinel-19f55.firebasestorage.app",
  messagingSenderId: "937459500646",
  appId: "1:937459500646:web:642cf2f3743984ab9ccfa7"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const { title, body } = payload.notification;
  self.registration.showNotification(title, {
    body,
    icon: "/icon.png",
    badge: "/icon.png"
  });
});
