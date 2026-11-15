import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import GithubProvider from "next-auth/providers/github";
import CredentialsProvider from "next-auth/providers/credentials";

const handler = NextAuth({
  providers: [
    // Local demo login so the cart works without OAuth credentials.
    CredentialsProvider({
      id: "demo",
      name: "Demo shopper",
      credentials: {},
      async authorize() {
        return {
          id: "demo",
          name: "Demo Shopper",
          email: "demo@grocergo.local",
          image: "/images/login/giticon.png",
        };
      },
    }),
    GoogleProvider({
      clientId: process.env.GOOGLE_ID as string,
      clientSecret: process.env.GOOGLE_SECRET as string,
    }),
    GithubProvider({
      clientId: process.env.GITHUB_ID as string,
      clientSecret: process.env.GITHUB_SECRET as string,
    }),
  ],
});

export { handler as GET, handler as POST };
