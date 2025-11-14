import { db } from "./firebase.js";
import { collection, getDocs } from "firebase/firestore";

async function getSocietyData() {
  try {
    const querySnapshot = await getDocs(collection(db, "society"));
    querySnapshot.forEach((doc) => {
      console.log(doc.id, "=>", doc.data());
    });
  } catch (error) {
    console.error("Error getting documents: ", error);
  }
}

getSocietyData();
